"""CLI: python -m autoclipper <url-youtube atau file lokal> [opsi]"""
import argparse
import json
import re
import shutil
import time
from pathlib import Path

from . import captions
from .download import download
from .highlights import find_highlights
from .reframe import crop_box
from .render import render_clip
from .transcribe import DEFAULT_MODEL, transcribe


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "clip"


def step(msg: str) -> float:
    print(f"\n▶ {msg}", flush=True)
    return time.time()


def main() -> None:
    p = argparse.ArgumentParser(description="Auto clip YouTube jadi video vertikal + caption.")
    p.add_argument("source", help="URL YouTube atau path file video lokal")
    p.add_argument("-n", "--clips", type=int, default=5, help="jumlah klip (default 5)")
    p.add_argument("--min", type=float, default=20, help="durasi minimal klip, detik")
    p.add_argument("--max", type=float, default=60, help="durasi maksimal klip, detik")
    p.add_argument("--lang", default=None, help="kode bahasa, mis. id / en (default: auto-detect)")
    p.add_argument("--llm", choices=["claude", "ollama"], default="claude", help="AI untuk memilih highlight")
    p.add_argument("--llm-model", default=None, help="mis. sonnet / haiku (claude) atau qwen2.5:7b (ollama)")
    p.add_argument("--whisper-model", default=DEFAULT_MODEL)
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--reselect", action="store_true", help="pilih ulang highlight (abaikan cache)")
    p.add_argument("--work", type=Path, default=Path("work"))
    p.add_argument("--out", type=Path, default=Path("output"))
    args = p.parse_args()

    t = step("Download video")
    video, vid, title = download(args.source, args.work)
    job = args.work / vid
    job.mkdir(parents=True, exist_ok=True)
    print(f"  {title} ({time.time() - t:.0f}s)")

    t = step("Transkripsi (Whisper)")
    segments = transcribe(video, job / "transcript.json", args.lang, args.whisper_model)
    print(f"  {len(segments)} segmen ({time.time() - t:.0f}s)")

    t = step(f"Cari highlight ({args.llm})")
    hl_cache = job / "highlights.json"
    if hl_cache.exists() and not args.reselect:
        clips = json.loads(hl_cache.read_text())
    else:
        clips = find_highlights(segments, title, args.clips, args.min, args.max, args.llm, args.llm_model)
        hl_cache.write_text(json.dumps(clips, ensure_ascii=False, indent=2))
    for i, c in enumerate(clips, 1):
        print(f"  {i}. [{c['start']:.0f}s-{c['end']:.0f}s] ({c.get('score', '?')}) {c['title']}")
    print(f"  ({time.time() - t:.0f}s)")

    out_dir = args.out / vid
    for i, c in enumerate(clips, 1):
        t = step(f"Render klip {i}/{len(clips)}: {c['title']}")
        crop = crop_box(video, c["start"], c["end"])
        cap_dir = job / f"captions_{i:02d}"
        cap = None if args.no_captions else captions.build(segments, c["start"], c["end"], cap_dir)
        out = out_dir / f"{i:02d}_{slug(c['title'])}.mp4"
        render_clip(video, c["start"], c["end"], crop, cap, out)
        shutil.rmtree(cap_dir, ignore_errors=True)
        c["file"] = str(out)
        print(f"  → {out} ({time.time() - t:.0f}s)")

    (out_dir / "clips.json").write_text(json.dumps(clips, ensure_ascii=False, indent=2))
    print(f"\n✅ Selesai! {len(clips)} klip di {out_dir}/")


if __name__ == "__main__":
    main()
