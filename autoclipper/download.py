import os
import re
from pathlib import Path

from .render import check_complete


def download(source: str, dest: Path, on_progress=None) -> tuple[Path, str]:
    """Download a video to dest/source.mp4 (or use a local file). Returns (path, title)."""
    local = Path(source).expanduser()
    if local.exists():
        return local.resolve(), local.stem

    if not re.match(r"https?://", source):
        raise ValueError("Invalid source: use an http(s) video link, or the path of a local video file that exists.")

    import yt_dlp

    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "source.mp4"
    opts = {
        # Prefer H.264 (most compatible), fall back to other codecs
        "format": "bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "outtmpl": str(dest / "source.%(ext)s"),
        # yt-dlp silently skips failed fragments by default, which leaves holes in the video. Don't.
        "skip_unavailable_fragments": False,
        "retries": 20,
        "fragment_retries": 50,
        "socket_timeout": 60,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if os.environ.get("AUTOCLIPPER_COOKIES"):
        opts["cookiefile"] = os.environ["AUTOCLIPPER_COOKIES"]
    if on_progress:
        def hook(d: dict) -> None:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if d["status"] == "downloading" and total:
                on_progress(f"{d.get('downloaded_bytes', 0) / total * 100:.0f}%")

        opts["progress_hooks"] = [hook]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=not out.exists())
    try:
        check_complete(out)
    except RuntimeError:
        out.unlink(missing_ok=True)  # so the next attempt downloads again
        raise
    return out.resolve(), info.get("title") or dest.name
