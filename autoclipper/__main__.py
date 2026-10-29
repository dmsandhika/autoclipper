"""CLI: python -m autoclipper <url-youtube atau file lokal> [opsi]"""
import argparse

from . import pipeline
from .transcribe import DEFAULT_MODEL


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
    p.add_argument("--reselect", action="store_true", help="pilih ulang highlight (abaikan hasil sebelumnya)")
    args = p.parse_args()

    job = pipeline.new_job(
        args.source,
        n=args.clips,
        min=args.min,
        max=args.max,
        lang=args.lang,
        llm=args.llm,
        llm_model=args.llm_model,
        whisper_model=args.whisper_model,
        captions=not args.no_captions,
    )
    pipeline.run(job, reselect=args.reselect)


if __name__ == "__main__":
    main()
