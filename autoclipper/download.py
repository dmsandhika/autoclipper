from pathlib import Path

from .render import check_complete


def download(source: str, dest: Path, on_progress=None) -> tuple[Path, str]:
    """Download video dari URL ke dest/source.mp4 (atau pakai file lokal). Return (path, judul)."""
    local = Path(source).expanduser()
    if local.exists():
        return local.resolve(), local.stem

    import yt_dlp

    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "source.mp4"
    opts = {
        # Utamakan H.264 (paling kompatibel), lalu codec lain kalau tidak ada
        "format": "bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "outtmpl": str(dest / "source.%(ext)s"),
        # Default yt-dlp diam-diam melewati potongan yang gagal → video bolong. Jangan.
        "skip_unavailable_fragments": False,
        "retries": 20,
        "fragment_retries": 50,
        "socket_timeout": 60,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
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
        out.unlink(missing_ok=True)  # supaya percobaan berikutnya download ulang
        raise
    return out.resolve(), info.get("title") or dest.name
