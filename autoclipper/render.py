import subprocess
from pathlib import Path

from .captions import HEIGHT as CAPTION_H

OUT_W, OUT_H = 1080, 1920
CAPTION_Y = int(OUT_H * 0.68) - CAPTION_H // 2


def render_clip(
    video: Path,
    start: float,
    end: float,
    crop: tuple[int, int, int, int] | None,
    captions: Path | None,
    out: Path,
) -> None:
    if crop:
        w, h, x, y = crop
        base = f"crop={w}:{h}:{x}:{y},scale={OUT_W}:{OUT_H}"
    else:
        base = f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2"
    base += ",setsar=1"

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", str(video)]
    if captions:
        cmd += ["-f", "concat", "-safe", "0", "-i", str(captions)]
        graph = f"[0:v]{base}[bg];[1:v]format=rgba[cap];[bg][cap]overlay=0:{CAPTION_Y}:format=auto,format=yuv420p[v]"
    else:
        graph = f"[0:v]{base},format=yuv420p[v]"
    cmd += [
        "-t", f"{end - start:.3f}",
        "-filter_complex", graph,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(out),
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
