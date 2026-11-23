"""Local web UI: python -m autoclipper.web  ->  open http://127.0.0.1:8765"""
import argparse
import base64
import os
import queue
import re
import secrets
import shutil
import tempfile
import threading
import traceback
import webbrowser
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, model_validator
from starlette.background import BackgroundTask

from . import __version__
from . import pipeline as pl
from .config import OUT, WORK, missing_binaries
from .highlights import default_llm, default_llm_model, llm_status
from .transcribe import DEFAULT_MODEL, backend_info

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="AutoClipper", version=__version__)
app.state.allow_local = os.environ.get("AUTOCLIPPER_ALLOW_LOCAL") == "1"
PASSWORD = os.environ.get("AUTOCLIPPER_PASSWORD")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Optional password (AUTOCLIPPER_PASSWORD) for when the UI is reachable beyond localhost."""
    if PASSWORD and request.url.path != "/api/health":
        try:
            given = base64.b64decode(request.headers.get("authorization", "")[6:]).decode().partition(":")[2]
        except Exception:
            given = ""
        if not secrets.compare_digest(given.encode(), PASSWORD.encode()):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="AutoClipper"'})
    return await call_next(request)


# All heavy work (download, whisper, render) runs one at a time on a single worker thread
tasks: queue.Queue = queue.Queue()


def worker() -> None:
    while True:
        fn, args = tasks.get()
        try:
            fn(*args)
        except Exception:
            traceback.print_exc()  # the job/clip already carries a user-facing error


JOBS: dict[str, dict] = {}
for _job in pl.list_jobs():
    if _job["status"] in pl.BUSY:
        _job.update(status="error", error="Interrupted because the server was stopped. Press Retry to continue.")
    for _c in _job["clips"]:
        if _c["status"] in {"pending", "queued", "rendering"}:
            _c.update(status="error", error="Interrupted. Save the clip again from the editor to re-render it.")
    JOBS[_job["id"]] = _job

threading.Thread(target=worker, daemon=True).start()

URL_RE = re.compile(r"^https?://\S+$")


class JobIn(BaseModel):
    source: str = Field(max_length=2000)
    n: int = Field(5, ge=1, le=20)
    min: float = Field(20, ge=5, le=170)
    max: float = Field(60, ge=10, le=180)
    lang: str | None = Field(None, pattern=r"^[a-z]{2,3}$")
    llm: Literal["claude", "anthropic", "openai", "ollama"] | None = None
    captions: bool = True

    @model_validator(mode="after")
    def _order(self):
        if self.max <= self.min:
            raise ValueError("Max duration must be greater than min duration")
        return self


class ClipIn(BaseModel):
    start: float
    end: float
    title: str = Field("Clip", max_length=200)
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
        raise HTTPException(404, "Project not found")
    return job


def get_clip(job: dict, cid: str) -> dict:
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "Clip not found")
    return clip


def require_video(job: dict) -> None:
    if not job.get("video") or not pl.transcript_path(job["id"]).exists():
        raise HTTPException(409, "The video has not finished downloading and transcribing yet")


def validate_range(body: ClipIn) -> None:
    if body.start < 0 or body.end <= body.start:
        raise HTTPException(400, "Start must be before end")
    if body.end - body.start > 180:
        raise HTTPException(400, "A clip can be at most 3 minutes long")


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


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/config")
def get_config():
    """What the UI needs to explain the setup and to block jobs that cannot work."""
    llm = default_llm()
    ok, problem = llm_status(llm)
    whisper = backend_info(DEFAULT_MODEL)
    return {
        "version": __version__,
        "missing": missing_binaries(),
        "llm": {"name": llm, "model": default_llm_model(), "ok": ok, "problem": problem},
        "whisper": whisper,
        "allow_local": app.state.allow_local,
        "auth": bool(PASSWORD),
    }


def check_ready(llm: str | None) -> None:
    if missing := missing_binaries():
        raise HTTPException(503, f"{', '.join(missing)} not found on PATH. Install ffmpeg and restart.")
    ok, problem = llm_status(llm)
    if not ok:
        raise HTTPException(400, problem)
    whisper = backend_info(DEFAULT_MODEL)
    if not whisper["ok"]:
        raise HTTPException(503, whisper["problem"])


@app.post("/api/jobs")
def create_job(body: JobIn):
    source = body.source.strip()
    if not source:
        raise HTTPException(400, "Paste a video link first")
    if not URL_RE.match(source):
        if not app.state.allow_local:
            raise HTTPException(400, "Enter a valid http(s) video link. Local file paths are disabled on this server.")
        if not Path(source).expanduser().is_file():
            raise HTTPException(400, "Enter a valid http(s) link or the path of an existing video file")
    existing = JOBS.get(pl.job_id(source))
    if existing and existing["status"] in pl.BUSY:
        raise HTTPException(409, "This video is already being processed")
    check_ready(body.llm)
    job = pl.new_job(
        source, existing, n=body.n, min=body.min, max=body.max, lang=body.lang, llm=body.llm, captions=body.captions
    )
    JOBS[job["id"]] = job
    tasks.put((pl.run, (job,)))
    return job


@app.post("/api/jobs/{jid}/retry")
def retry(jid: str):
    job = get_job(jid)
    if job["status"] in pl.BUSY:
        raise HTTPException(409, "This project is being processed")
    check_ready(job["opts"].get("llm"))
    job.update(status="queued", error=None)
    pl.save_job(job)
    tasks.put((pl.run, (job,)))
    return job


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str):
    job = get_job(jid)
    if job["status"] in pl.BUSY or any(c["status"] in {"queued", "rendering"} for c in job["clips"]):
        raise HTTPException(409, "Wait until processing has finished before deleting this project")
    for root in (WORK, OUT):
        target = (root / job["id"]).resolve()
        if target.parent == root.resolve():
            shutil.rmtree(target, ignore_errors=True)
    JOBS.pop(jid, None)
    return {"ok": True}


@app.get("/api/jobs/{jid}/zip")
def clips_zip(jid: str):
    job = get_job(jid)
    files = [Path(c["file"]) for c in job["clips"] if c["status"] == "ready" and c.get("file") and Path(c["file"]).exists()]
    if not files:
        raise HTTPException(404, "There are no rendered clips to download yet")
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as z:  # mp4 is already compressed
        for f in files:
            z.write(f, f.name)
    name = f"{pl.slug(job['title'])}-clips.zip"
    return FileResponse(tmp.name, filename=name, media_type="application/zip", background=BackgroundTask(os.unlink, tmp.name))


@app.post("/api/jobs/{jid}/reselect")
def reselect(jid: str):
    job = get_job(jid)
    if job["status"] in pl.BUSY:
        raise HTTPException(409, "This project is being processed")
    require_video(job)
    check_ready(job["opts"].get("llm"))
    job.update(status="queued", error=None)
    pl.save_job(job)
    tasks.put((pl.run, (job, True)))
    return job


@app.get("/api/jobs/{jid}/video")
def source_video(jid: str):
    job = get_job(jid)
    if not job.get("video") or not Path(job["video"]).exists():
        raise HTTPException(404, "The source video is not available")
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
            raise HTTPException(400, f"Word {e.seg}/{e.idx} does not exist")
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
    clip = pl.new_clip(body.start, body.end, body.title.strip() or "Clip", captions=body.captions)
    job["clips"].append(clip)
    queue_render(job, clip)
    return clip


@app.put("/api/jobs/{jid}/clips/{cid}")
def update_clip(jid: str, cid: str, body: ClipIn):
    job = get_job(jid)
    clip = get_clip(job, cid)
    if clip["status"] in {"queued", "rendering"}:
        raise HTTPException(409, "This clip is being rendered")
    validate_range(body)
    clip.update(start=body.start, end=body.end, title=body.title.strip() or "Clip", captions=body.captions)
    queue_render(job, clip)
    return clip


@app.delete("/api/jobs/{jid}/clips/{cid}")
def delete_clip(jid: str, cid: str):
    job = get_job(jid)
    clip = get_clip(job, cid)
    if clip["status"] == "rendering":
        raise HTTPException(409, "This clip is being rendered")
    job["clips"].remove(clip)
    if clip.get("file"):
        Path(clip["file"]).unlink(missing_ok=True)
    pl.save_job(job)
    return {"ok": True}


@app.get("/api/jobs/{jid}/clips/{cid}/file")
def clip_file(jid: str, cid: str, dl: bool = False):
    clip = get_clip(get_job(jid), cid)
    if not clip.get("file") or not Path(clip["file"]).exists():
        raise HTTPException(404, "This clip has not been rendered yet")
    return FileResponse(clip["file"], filename=Path(clip["file"]).name if dl else None)


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(description="AutoClipper web UI")
    p.add_argument("--host", default=os.environ.get("AUTOCLIPPER_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("AUTOCLIPPER_PORT", "8765")))
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    loopback = args.host in {"127.0.0.1", "localhost", "::1"}
    if loopback:
        app.state.allow_local = True  # local file paths are only safe when nobody else can reach the server
    elif not PASSWORD:
        print("! Warning: the server is reachable from other machines and has no password. "
              "Set AUTOCLIPPER_PASSWORD or keep it behind localhost.")
    if missing := missing_binaries():
        print(f"! Warning: {', '.join(missing)} not found on PATH. Jobs will be refused until ffmpeg is installed.")
    url = f"http://{args.host}:{args.port}"
    print(f"AutoClipper running at {url}")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
