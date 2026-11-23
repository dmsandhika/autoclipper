"""CLI: python -m autoclipper <youtube url or local file> [options]"""
import argparse
import sys

from . import pipeline
from .config import missing_binaries
from .errors import explain
from .highlights import LLMS, default_llm, llm_status
from .transcribe import DEFAULT_MODEL


def main() -> None:
    p = argparse.ArgumentParser(description="Turn a YouTube video into vertical clips with captions.")
    p.add_argument("source", help="YouTube URL or path to a local video file")
    p.add_argument("-n", "--clips", type=int, default=5, help="number of clips (default 5)")
    p.add_argument("--min", type=float, default=20, help="minimum clip length in seconds")
    p.add_argument("--max", type=float, default=60, help="maximum clip length in seconds")
    p.add_argument("--lang", default=None, help="language code, e.g. id / en (default: auto-detect)")
    p.add_argument("--llm", choices=LLMS, default=None, help="AI that picks highlights (default: env AUTOCLIPPER_LLM, else auto)")
    p.add_argument("--llm-model", default=None, help="e.g. haiku (claude CLI), claude-haiku-5-5 (anthropic), qwen2.5:7b (ollama)")
    p.add_argument("--whisper-model", default=DEFAULT_MODEL, help="e.g. small / large-v3 (default: automatic)")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--reselect", action="store_true", help="pick highlights again, ignoring earlier results")
    args = p.parse_args()

    if missing := missing_binaries():
        sys.exit(f"error: {', '.join(missing)} not found on PATH. Install ffmpeg first.")
    ok, problem = llm_status(args.llm)
    if not ok:
        sys.exit(f"error: AI '{args.llm or default_llm()}' is not usable: {problem}")

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
    try:
        pipeline.run(job, reselect=args.reselect)
    except Exception as e:
        sys.exit(f"error: {explain(e)}")


if __name__ == "__main__":
    main()
