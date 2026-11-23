import json

from autoclipper import transcribe as t


def test_empty_cache_is_ignored_and_not_rewritten(tmp_path, monkeypatch):
    cache = tmp_path / "transcript.json"
    cache.write_text("[]")
    calls = []

    def fake(video, language, model):
        calls.append(1)
        return [], None

    monkeypatch.setattr(t, "_use_mlx", lambda: False)
    monkeypatch.setattr(t, "_run_faster", fake)
    assert t.transcribe(tmp_path / "v.mp4", cache) == []
    assert calls == [1]  # the empty cache did not short-circuit the run
    assert not cache.exists()  # the useless empty cache was removed, nothing new was cached


def test_non_empty_result_is_cached(tmp_path, monkeypatch):
    cache = tmp_path / "transcript.json"
    raw = [{"start": 0.0, "end": 2.0, "text": " hi there ", "words": [{"word": " hi", "start": 0.0, "end": 1.0}]}]
    monkeypatch.setattr(t, "_use_mlx", lambda: False)
    monkeypatch.setattr(t, "_run_faster", lambda *a: (raw, "id"))
    out = t.transcribe(tmp_path / "v.mp4", cache)
    assert out[0]["text"] == "hi there" and json.loads(cache.read_text()) == out
    monkeypatch.setattr(t, "_run_faster", lambda *a: 1 / 0)  # must not run again
    assert t.transcribe(tmp_path / "v.mp4", cache) == out


def test_changing_language_invalidates_cache(tmp_path, monkeypatch):
    cache = tmp_path / "transcript.json"
    raw = [{"start": 0.0, "end": 2.0, "text": "hello", "words": []}]
    monkeypatch.setattr(t, "_use_mlx", lambda: False)
    monkeypatch.setattr(t, "_run_faster", lambda *a: (raw, "en"))
    t.transcribe(tmp_path / "v.mp4", cache)  # auto-detected as English
    assert t.detected_language(cache) == "en"
    assert t.cache_valid(cache, None) and t.cache_valid(cache, "en")
    assert not t.cache_valid(cache, "id")  # user now says it is Indonesian -> must re-run
    assert t._read_meta(cache) == {"language": "en", "model": t.DEFAULT_MODEL}
