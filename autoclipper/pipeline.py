"""Pipeline auto clip yang dipakai bersama oleh CLI dan web.

State tiap project disimpan di work/<id>/job.json, hasil klip di output/<id>/.
"""
import hashlib
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from . import captions
from .download import download
from .highlights import find_highlights
from .reframe import crop_box
from .render import render_clip
from .transcribe import DEFAULT_MODEL, transcribe

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
OUT = ROOT / "output"
DEFAULT_OPTS = {
    "n": 5,
    "min": 20,
    "max": 60,
    "lang": None,
    "llm": "claude",
    "llm_model": None,
    "whisper_model": DEFAULT_MODEL,
    "captions": True,
}
BUSY = {"queued", "downloading", "transcribing", "selecting", "rendering"}
_save_lock = threading.Lock()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "clip"


def job_id(source: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([\w-]{11})", source)
    if m:
        return m.group(1)
    local = Path(source).expanduser()
    if local.exists():
        return slug(local.stem)
    return hashlib.sha1(source.encode()).hexdigest()[:11]


def job_dir(jid: str) -> Path:
    return WORK / jid


def transcript_path(jid: str) -> Path:
    return job_dir(jid) / "transcript.json"


def load_transcript(jid: str) -> list[dict]:
    return json.loads(transcript_path(jid).read_text())


def save_transcript(jid: str, segments: list[dict]) -> None:
    transcript_path(jid).write_text(json.dumps(segments, ensure_ascii=False, indent=1))


def load_job(jid: str) -> dict | None:
    p = job_dir(jid) / "job.json"
    return json.loads(p.read_text()) if p.exists() else None


def list_jobs() -> list[dict]:
    return [json.loads(p.read_text()) for p in WORK.glob("*/job.json")]


def save_job(job: dict) -> None:
    p = job_dir(job["id"]) / "job.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with _save_lock:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2))
        tmp.replace(p)


def new_job(source: str, existing: dict | None = None, **opts) -> dict:
    jid = job_id(source)
    job = existing or load_job(jid) or {"id": jid, "source": source, "title": jid, "created": time.time(), "clips": []}
    job["opts"] = {**DEFAULT_OPTS, **job.get("opts", {}), **{k: v for k, v in opts.items() if v is not None}}
    job.update(status="queued", error=None)
    save_job(job)
    return job


def new_clip(start: float, end: float, title: str = "Klip", **extra) -> dict:
    return {
        "id": uuid.uuid4().hex[:6],
        "start": float(start),
        "end": float(end),
        "title": title,
        "captions": True,
        "status": "pending",
        **extra,
    }


def run(job: dict, reselect: bool = False, log=print) -> dict:
    """Jalankan seluruh pipeline. Tahap yang sudah ada hasilnya (download, transkrip, klip) di-skip."""
    o = job["opts"]

    def stage(status: str, msg: str) -> None:
        job["status"] = status
        save_job(job)
        log(f"\n▶ {msg}")

    try:
        stage("downloading", "Download video")
        video, title = download(job["source"], job_dir(job["id"]))
        job.update(video=str(video), title=title)

        stage("transcribing", "Transkripsi (Whisper)")
        segments = transcribe(video, transcript_path(job["id"]), o["lang"], o["whisper_model"])

        if reselect or not job["clips"]:
            stage("selecting", f"Cari highlight ({o['llm']})")
            for old in job["clips"]:
                if old.get("file"):
                    Path(old["file"]).unlink(missing_ok=True)
            found = find_highlights(segments, title, o["n"], o["min"], o["max"], o["llm"], o["llm_model"])
            job["clips"] = [
                new_clip(
                    c["start"],
                    c["end"],
                    c.get("title") or "Klip",
                    captions=o["captions"],
                    **{k: c.get(k) for k in ("hook", "reason", "score")},
                )
                for c in found
            ]
            for i, c in enumerate(job["clips"], 1):
                log(f"  {i}. [{c['start']:.0f}s-{c['end']:.0f}s] ({c.get('score') or '?'}) {c['title']}")

        stage("rendering", f"Render {len(job['clips'])} klip")
        for clip in job["clips"]:
            if clip["status"] != "ready":
                render(job, clip, log)

        stage("done", f"Selesai! Klip ada di {OUT / job['id']}/")
    except Exception as e:
        job.update(status="error", error=str(e))
        save_job(job)
        raise
    return job


def render(job: dict, clip: dict, log=print) -> None:
    jid = job["id"]
    clip.update(status="rendering", error=None)
    save_job(job)
    cap_dir = job_dir(jid) / f"captions_{clip['id']}"
    t = time.time()
    try:
        video = Path(job["video"])
        crop = crop_box(video, clip["start"], clip["end"])
        cap = None
        if clip.get("captions", True):
            cap = captions.build(load_transcript(jid), clip["start"], clip["end"], cap_dir)
        out = OUT / jid / f"{clip['id']}_{slug(clip['title'])}.mp4"
        if clip.get("file") and Path(clip["file"]) != out:
            Path(clip["file"]).unlink(missing_ok=True)
        render_clip(video, clip["start"], clip["end"], crop, cap, out)
        clip.update(file=str(out), status="ready", rendered=time.time())
        log(f"  → {out} ({time.time() - t:.0f}s)")
    except Exception as e:
        clip.update(status="error", error=str(e))
        raise
    finally:
        shutil.rmtree(cap_dir, ignore_errors=True)
        save_job(job)
