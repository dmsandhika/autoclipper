"""Web UI lokal: python -m autoclipper.web  → buka http://127.0.0.1:8765"""
import argparse
import queue
import threading
import traceback
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import pipeline as pl

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="AutoClipper")

# Semua proses berat (download, whisper, render) jalan berurutan di satu worker thread
tasks: queue.Queue = queue.Queue()


def worker() -> None:
    while True:
        fn, args = tasks.get()
        try:
            fn(*args)
        except Exception:
            traceback.print_exc()


JOBS: dict[str, dict] = {}
for _job in pl.list_jobs():
    if _job["status"] in pl.BUSY:
        _job.update(status="error", error="Terhenti karena server dimatikan")
    for _c in _job["clips"]:
        if _c["status"] in {"pending", "queued", "rendering"}:
            _c.update(status="error", error="Terhenti, simpan ulang dari editor untuk render")
    JOBS[_job["id"]] = _job

threading.Thread(target=worker, daemon=True).start()


class JobIn(BaseModel):
    source: str
    n: int = 5
    min: float = 20
    max: float = 60
    lang: str | None = None
    llm: str = "claude"
    captions: bool = True


class ClipIn(BaseModel):
    start: float
    end: float
    title: str = "Klip"
    captions: bool = True


class WordEdit(BaseModel):
    seg: int
    idx: int
    word: str


class TranscriptPatch(BaseModel):
    edits: list[WordEdit]


def get_job(jid: str) -> dict:
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Project tidak ditemukan")
    return job


def get_clip(job: dict, cid: str) -> dict:
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "Klip tidak ditemukan")
    return clip


def require_video(job: dict) -> None:
    if not job.get("video") or not pl.transcript_path(job["id"]).exists():
        raise HTTPException(409, "Video belum selesai didownload/ditranskrip")


def validate_range(body: ClipIn) -> None:
    if body.start < 0 or body.end <= body.start:
        raise HTTPException(400, "Waktu mulai harus lebih kecil dari waktu selesai")
    if body.end - body.start > 180:
        raise HTTPException(400, "Durasi klip maksimal 3 menit")


def queue_render(job: dict, clip: dict) -> None:
    clip.update(status="queued", error=None)
    pl.save_job(job)
    tasks.put((pl.render, (job, clip)))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/jobs")
def list_jobs():
    return sorted(JOBS.values(), key=lambda j: -j.get("created", 0))


@app.post("/api/jobs")
def create_job(body: JobIn):
    source = body.source.strip()
    if not source:
        raise HTTPException(400, "Link video kosong")
    existing = JOBS.get(pl.job_id(source))
    if existing and existing["status"] in pl.BUSY:
        raise HTTPException(409, "Video ini sedang diproses")
    job = pl.new_job(
        source, existing, n=body.n, min=body.min, max=body.max, lang=body.lang, llm=body.llm, captions=body.captions
    )
    JOBS[job["id"]] = job
    tasks.put((pl.run, (job,)))
    return job


@app.post("/api/jobs/{jid}/reselect")
def reselect(jid: str):
    job = get_job(jid)
    if job["status"] in pl.BUSY:
        raise HTTPException(409, "Project sedang diproses")
    job.update(status="queued", error=None)
    pl.save_job(job)
    tasks.put((pl.run, (job, True)))
    return job


@app.get("/api/jobs/{jid}/video")
def source_video(jid: str):
    job = get_job(jid)
    if not job.get("video") or not Path(job["video"]).exists():
        raise HTTPException(404, "Video sumber belum ada")
    return FileResponse(job["video"])


@app.get("/api/jobs/{jid}/transcript")
def get_transcript(jid: str):
    job = get_job(jid)
    require_video(job)
    return pl.load_transcript(jid)


@app.patch("/api/jobs/{jid}/transcript")
def patch_transcript(jid: str, body: TranscriptPatch):
    job = get_job(jid)
    require_video(job)
    segments = pl.load_transcript(jid)
    for e in body.edits:
        try:
            word = segments[e.seg]["words"][e.idx]
        except IndexError:
            raise HTTPException(400, f"Kata {e.seg}/{e.idx} tidak ada")
        word["word"] = e.word.strip() or word["word"]
    for si in {e.seg for e in body.edits}:
        segments[si]["text"] = " ".join(w["word"] for w in segments[si]["words"])
    pl.save_transcript(jid, segments)
    return {"ok": True}


@app.post("/api/jobs/{jid}/clips")
def add_clip(jid: str, body: ClipIn):
    job = get_job(jid)
    require_video(job)
    validate_range(body)
    clip = pl.new_clip(body.start, body.end, body.title.strip() or "Klip", captions=body.captions)
    job["clips"].append(clip)
    queue_render(job, clip)
    return clip


@app.put("/api/jobs/{jid}/clips/{cid}")
def update_clip(jid: str, cid: str, body: ClipIn):
    job = get_job(jid)
    clip = get_clip(job, cid)
    if clip["status"] in {"queued", "rendering"}:
        raise HTTPException(409, "Klip ini sedang dirender")
    validate_range(body)
    clip.update(start=body.start, end=body.end, title=body.title.strip() or "Klip", captions=body.captions)
    queue_render(job, clip)
    return clip


@app.delete("/api/jobs/{jid}/clips/{cid}")
def delete_clip(jid: str, cid: str):
    job = get_job(jid)
    clip = get_clip(job, cid)
    if clip["status"] == "rendering":
        raise HTTPException(409, "Klip ini sedang dirender")
    job["clips"].remove(clip)
    if clip.get("file"):
        Path(clip["file"]).unlink(missing_ok=True)
    pl.save_job(job)
    return {"ok": True}


@app.get("/api/jobs/{jid}/clips/{cid}/file")
def clip_file(jid: str, cid: str, dl: bool = False):
    clip = get_clip(get_job(jid), cid)
    if not clip.get("file") or not Path(clip["file"]).exists():
        raise HTTPException(404, "Klip belum dirender")
    return FileResponse(clip["file"], filename=Path(clip["file"]).name if dl else None)


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(description="AutoClipper web UI")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    print(f"AutoClipper jalan di {url}")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
