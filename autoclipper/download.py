from pathlib import Path


def download(source: str, work_dir: Path) -> tuple[Path, str, str]:
    """Download video dari URL (atau pakai file lokal). Return (path, id, judul)."""
    local = Path(source).expanduser()
    if local.exists():
        return local, local.stem, local.stem

    import yt_dlp

    work_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(work_dir / "%(id)s" / "source.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=False)
        path = work_dir / info["id"] / "source.mp4"
        if not path.exists():
            ydl.download([source])
    return path, info["id"], info.get("title", info["id"])
