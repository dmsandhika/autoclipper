import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture()
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIPPER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("AUTOCLIPPER_LLM", "anthropic")
    import autoclipper.config, autoclipper.pipeline as pl

    for m in (autoclipper.config, pl):
        importlib.reload(m)
    return pl


def test_pipeline_regenerates_and_reselects_when_cache_invalid(pipeline, monkeypatch):
    pl = pipeline

    # Fake download
    monkeypatch.setattr(pl, "download", lambda src, jdir, cb: (jdir / "video.mp4", "Test Video"))
    # Fake highlights
    found_calls = []
    def fake_highlights(segments, title, n, min_d, max_d, llm, llm_model):
        found_calls.append(segments[0]["text"])
        return [{"start": 0.0, "end": 5.0, "title": "Clip", "score": 90}]
    monkeypatch.setattr(pl, "find_highlights", fake_highlights)
    # Fake render
    monkeypatch.setattr(pl, "render", lambda job, clip, log=print: clip.update(status="ready"))

    # Initial job with clips already existing
    job = pl.new_job("https://example.com/v")
    video_path = pl.job_dir(job["id"]) / "video.mp4"
    video_path.touch()
    tpath = pl.transcript_path(job["id"])
    tpath.write_text(json.dumps([{"start": 0.0, "end": 5.0, "text": "english text", "words": []}]))
    tpath.with_suffix(".meta.json").write_text(json.dumps({"language": "en", "model": None}))

    # Populate job with an old clip
    job["clips"] = [pl.new_clip(0.0, 5.0, "Old English Clip", status="ready")]
    job["opts"]["lang"] = "id"  # user switches language to Indonesian

    # Fake transcribe returns indonesian
    def fake_transcribe(video, cache, language, model):
        cache.write_text(json.dumps([{"start": 0.0, "end": 5.0, "text": "teks indonesia", "words": []}]))
        cache.with_suffix(".meta.json").write_text(json.dumps({"language": "id", "model": model}))
        return json.loads(cache.read_text())
    monkeypatch.setattr(pl, "transcribe", fake_transcribe)

    logs = []
    pl.run(job, log=logs.append)

    assert job["language"] == "id"
    assert any("language: id" in l for l in logs)
    assert found_calls == ["teks indonesia"]  # reselect occurred with new transcript
    assert job["status"] == "done"
