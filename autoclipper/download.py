from pathlib import Path


def download(source: str, dest: Path) -> tuple[Path, str]:
    """Download video dari URL ke dest/source.mp4 (atau pakai file lokal). Return (path, judul)."""
    local = Path(source).expanduser()
    if local.exists():
        return local.resolve(), local.stem

    import yt_dlp

    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "source.mp4"
    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "outtmpl": str(dest / "source.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=not out.exists())
    return out.resolve(), info.get("title") or dest.name
