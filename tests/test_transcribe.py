import json

from autoclipper import transcribe as t


def test_empty_cache_is_ignored_and_not_rewritten(tmp_path, monkeypatch):
    cache = tmp_path / "transcript.json"
    cache.write_text("[]")
    calls = []

    def fake(video, language, model):
        calls.append(1)
        return []

    monkeypatch.setattr(t, "_use_mlx", lambda: False)
    monkeypatch.setattr(t, "_run_faster", fake)
    assert t.transcribe(tmp_path / "v.mp4", cache) == []
    assert calls == [1]  # the empty cache did not short-circuit the run
    assert json.loads(cache.read_text()) == []  # and nothing new was cached


def test_non_empty_result_is_cached(tmp_path, monkeypatch):
    cache = tmp_path / "transcript.json"
    raw = [{"start": 0.0, "end": 2.0, "text": " hi there ", "words": [{"word": " hi", "start": 0.0, "end": 1.0}]}]
    monkeypatch.setattr(t, "_use_mlx", lambda: False)
    monkeypatch.setattr(t, "_run_faster", lambda *a: raw)
    out = t.transcribe(tmp_path / "v.mp4", cache)
    assert out[0]["text"] == "hi there" and json.loads(cache.read_text()) == out
    monkeypatch.setattr(t, "_run_faster", lambda *a: 1 / 0)  # must not run again
    assert t.transcribe(tmp_path / "v.mp4", cache) == out
