import json
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
    if video_frames(out) == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError("Hasil render tidak punya gambar. Video sumber kemungkinan rusak/tidak lengkap di bagian ini.")


def probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,nb_frames:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def video_frames(path: Path) -> int:
    streams = [s for s in probe(path).get("streams", []) if s["codec_type"] == "video"]
    return int(streams[0].get("nb_frames") or 0) if streams else 0


def check_complete(path: Path) -> None:
    """Pastikan track video tidak jauh lebih pendek dari durasi file (tanda download bolong)."""
    info = probe(path)
    total = float(info["format"]["duration"])
    video = [float(s.get("duration") or 0) for s in info["streams"] if s["codec_type"] == "video"]
    if not video or video[0] < total * 0.98 - 2:
        got = video[0] if video else 0
        raise RuntimeError(
            f"Video hasil download tidak lengkap (gambar {got / 60:.1f} dari {total / 60:.1f} menit). "
            "Kemungkinan koneksi putus, coba proses ulang."
        )
