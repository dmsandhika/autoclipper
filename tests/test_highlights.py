import json

import pytest

from autoclipper import highlights as h

SEGS = [{"start": float(i * 10), "end": float(i * 10 + 9), "text": f"sentence {i}", "words": []} for i in range(12)]


def test_parse_clips_extracts_json_and_drops_invalid():
    text = 'sure! {"clips": [{"start": 1, "end": 30, "title": "a"}, {"start": 5}, {"start": 9, "end": 3}]} bye'
    clips = h.parse_clips(text)
    assert [(c["start"], c["end"]) for c in clips] == [(1.0, 30.0)]


@pytest.mark.parametrize("bad", ["no json here", '{"clips": []}', '{"clips": [{"start": "x", "end": 2}]}'])
def test_parse_clips_rejects_unusable(bad):
    with pytest.raises(ValueError):
        h.parse_clips(bad)


def test_snap_aligns_to_segments_and_removes_overlap():
    clips = [{"start": 11, "end": 38, "score": 50}, {"start": 20, "end": 45, "score": 90}, {"start": 70, "end": 100, "score": 70}]
    out = h.snap(clips, SEGS, min_d=20, max_d=60)
    assert [(c["start"], c["end"]) for c in out] == [(70.0, 99.0), (10.0, 39.0)]  # sorted by score, overlap dropped


def test_chunk_segments_respects_limit():
    chunks = h.chunk_segments(SEGS, max_chars=100)
    assert len(chunks) > 1 and sum(map(len, chunks)) == len(SEGS)


def test_find_highlights_retries_once_then_succeeds(monkeypatch):
    calls = []

    def fake(prompt, model):
        calls.append(1)
        return "garbage" if len(calls) == 1 else json.dumps({"clips": [{"start": 10, "end": 39, "title": "x", "score": 80}]})

    monkeypatch.setattr(h, "ask_anthropic", fake)
    out = h.find_highlights(SEGS, "t", 1, 20, 60, llm="anthropic")
    assert len(calls) == 2 and out[0]["start"] == 10.0


def test_find_highlights_fails_clearly(monkeypatch):
    monkeypatch.setattr(h, "ask_anthropic", lambda p, m: "nope")
    with pytest.raises(RuntimeError, match="invalid response"):
        h.find_highlights(SEGS, "t", 1, 20, 60, llm="anthropic")
    with pytest.raises(RuntimeError, match="No speech"):
        h.find_highlights([], "t", 1, 20, 60, llm="anthropic")


def test_llm_status_reports_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ok, problem = h.llm_status("anthropic")
    assert not ok and "ANTHROPIC_API_KEY" in problem
