import json
import os
import platform
from pathlib import Path

# Kosong = pilih otomatis sesuai backend (MLX di Apple Silicon, faster-whisper di tempat lain)
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


def _run_mlx(video: Path, language: str | None, model: str | None) -> list[dict]:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(video), path_or_hf_repo=_mlx_repo(model), word_timestamps=True, language=language, verbose=False
    )
    return [
        {"start": s["start"], "end": s["end"], "text": s["text"], "words": s.get("words", [])}
        for s in result["segments"]
    ]


def _run_faster(video: Path, language: str | None, model: str | None) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Backend transkripsi belum terpasang: pip install faster-whisper") from e

    device = os.environ.get("AUTOCLIPPER_DEVICE", "auto")
    wm = WhisperModel(
        model or FASTER_DEFAULT,
        device=device,
        compute_type="default" if device == "cuda" else "int8" if device == "cpu" else "auto",
        download_root=os.environ.get("AUTOCLIPPER_MODEL_DIR") or None,
    )
    segments, _ = wm.transcribe(str(video), language=language, word_timestamps=True, vad_filter=True)
    return [
        {
            "start": s.start,
            "end": s.end,
            "text": s.text,
            "words": [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])],
        }
        for s in segments
    ]


def transcribe(video: Path, cache: Path, language: str | None = None, model: str | None = DEFAULT_MODEL) -> list[dict]:
    """Transkripsi dengan timestamp per kata. Hasil di-cache ke JSON."""
    if cache.exists():
        return json.loads(cache.read_text())

    raw = _run_mlx(video, language, model) if _use_mlx() else _run_faster(video, language, model)
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
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(segments, ensure_ascii=False, indent=1))
    return segments
