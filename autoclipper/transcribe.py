import json
from pathlib import Path

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def transcribe(video: Path, cache: Path, language: str | None = None, model: str = DEFAULT_MODEL) -> list[dict]:
    """Transkripsi dengan timestamp per kata. Hasil di-cache ke JSON."""
    if cache.exists():
        return json.loads(cache.read_text())

    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(video),
        path_or_hf_repo=model,
        word_timestamps=True,
        language=language,
        verbose=False,
    )
    segments = [
        {
            "start": round(s["start"], 2),
            "end": round(s["end"], 2),
            "text": s["text"].strip(),
            "words": [
                {"word": w["word"].strip(), "start": round(w["start"], 2), "end": round(w["end"], 2)}
                for w in s.get("words", [])
                if w["word"].strip()
            ],
        }
        for s in result["segments"]
        if s["text"].strip()
    ]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(segments, ensure_ascii=False, indent=1))
    return segments
