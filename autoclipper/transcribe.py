import json
import os
import platform
from pathlib import Path

# Empty = pick automatically per backend (MLX on Apple Silicon, faster-whisper elsewhere)
DEFAULT_MODEL = os.environ.get("AUTOCLIPPER_WHISPER_MODEL") or None
MLX_DEFAULT = "mlx-community/whisper-large-v3-turbo"
FASTER_DEFAULT = "small"


def _use_mlx() -> bool:
    if os.environ.get("AUTOCLIPPER_WHISPER_BACKEND", "auto") == "faster-whisper":
        return False
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return False
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _mlx_repo(model: str | None) -> str:
    if not model:
        return MLX_DEFAULT
    if "/" in model:
        return model
    return MLX_DEFAULT if model == "large-v3-turbo" else f"mlx-community/whisper-{model}-mlx"


def _run_mlx(video: Path, language: str | None, model: str | None) -> tuple[list[dict], str | None]:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(video), path_or_hf_repo=_mlx_repo(model), word_timestamps=True, language=language, verbose=False
    )
    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"], "words": s.get("words", [])}
        for s in result["segments"]
    ]
    return segments, result.get("language")


def _run_faster(video: Path, language: str | None, model: str | None) -> tuple[list[dict], str | None]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("No transcription backend installed. Run: pip install faster-whisper") from e

    device = os.environ.get("AUTOCLIPPER_DEVICE", "auto")
    wm = WhisperModel(
        model or FASTER_DEFAULT,
        device=device,
        compute_type="default" if device == "cuda" else "int8" if device == "cpu" else "auto",
        download_root=os.environ.get("AUTOCLIPPER_MODEL_DIR") or None,
    )
    # The VAD filter skips silence/music and speeds things up, but on quiet or noisy audio it can drop
    # everything. If it leaves nothing, try again without it.
    for vad in (True, False):
        # Voting over several 30s windows makes auto-detection far more reliable than the default single window
        segments, info = wm.transcribe(
            str(video), language=language, word_timestamps=True, vad_filter=vad, language_detection_segments=4
        )
        result = [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "words": [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])],
            }
            for s in segments
        ]
        print(f"  language: {info.language} ({info.language_probability:.0%}), vad={vad}, segments={len(result)}")
        if any(r["text"].strip() for r in result):
            return result, info.language
    return [], info.language


def _meta_path(cache: Path) -> Path:
    return cache.with_suffix(".meta.json")


def _read_meta(cache: Path) -> dict:
    try:
        return json.loads(_meta_path(cache).read_text())
    except (OSError, ValueError):
        return {}


def cache_valid(cache: Path, language: str | None = None, model: str | None = None) -> bool:
    """Is the cached transcript usable for these settings? Empty transcripts and ones made in
    another language/model than explicitly requested are not."""
    if not cache.exists():
        return False
    try:
        if not json.loads(cache.read_text()):
            return False
    except ValueError:
        return False
    meta = _read_meta(cache)
    if language and meta.get("language") != language:
        return False
    if model and meta.get("model") != model:
        return False
    return True


def detected_language(cache: Path) -> str | None:
    return _read_meta(cache).get("language")


def transcribe(video: Path, cache: Path, language: str | None = None, model: str | None = DEFAULT_MODEL) -> list[dict]:
    """Transcribe with word-level timestamps. The result is cached as JSON (plus a small meta file
    recording the language and model, so changing either re-runs the transcription)."""
    if cache_valid(cache, language, model):
        return json.loads(cache.read_text())

    raw, lang = _run_mlx(video, language, model) if _use_mlx() else _run_faster(video, language, model)
    segments = [
        {
            "start": round(s["start"], 2),
            "end": round(s["end"], 2),
            "text": s["text"].strip(),
            "words": [
                {"word": w["word"].strip(), "start": round(w["start"], 2), "end": round(w["end"], 2)}
                for w in s["words"]
                if w["word"].strip()
            ],
        }
        for s in raw
        if s["text"].strip()
    ]
    if segments:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(segments, ensure_ascii=False, indent=1))
        _meta_path(cache).write_text(json.dumps({"language": language or lang, "model": model}))
    else:
        cache.unlink(missing_ok=True)
        _meta_path(cache).unlink(missing_ok=True)
    return segments


def backend_info(model: str | None = DEFAULT_MODEL) -> dict:
    """Describe which transcription backend will be used (for the UI and health checks)."""
    from importlib.util import find_spec

    if _use_mlx():
        return {"name": "mlx-whisper", "model": _mlx_repo(model).split("/")[-1], "ok": True}
    ok = find_spec("faster_whisper") is not None
    return {"name": "faster-whisper", "model": model or FASTER_DEFAULT, "ok": ok,
            "problem": "" if ok else "faster-whisper is not installed (pip install faster-whisper)"}
