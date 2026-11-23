"""Pick the best moments from a transcript with an LLM.

Backends: claude (Claude Code CLI), anthropic (API), openai (OpenAI-compatible API), ollama (local).
Configured through environment variables, see .env.example.
"""
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request

LLMS = ["claude", "anthropic", "openai", "ollama"]
DEFAULT_MODELS = {
    "claude": None,
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
    "ollama": "qwen2.5:7b",
}


def default_llm() -> str:
    """AUTOCLIPPER_LLM if set; otherwise guess from what is available."""
    env = os.environ.get("AUTOCLIPPER_LLM")
    if env:
        return env
    if shutil.which("claude"):
        return "claude"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "ollama"


def default_llm_model() -> str | None:
    return os.environ.get("AUTOCLIPPER_LLM_MODEL") or None

PROMPT = """You are an editor of short-form video (TikTok/Reels/Shorts) who knows what goes viral.

Below is the transcript of a video titled "{title}". Each line is: [start_seconds-end_seconds] text.

Pick the {n} best moments to turn into short clips. Criteria:
- Each clip is {min_d}-{max_d} seconds long.
- It opens with a strong hook in the first 3 seconds (a question, a surprising statement, a bold opinion, a gripping story).
- It makes sense on its own, without the context of the full video.
- It ends on a complete sentence, never mid-sentence.
- Clips must not overlap.
- Write "title", "hook" and "reason" in the same language as the transcript.

Answer with JSON ONLY (no other text, no markdown) in this format:
{{"clips": [{{"start": 12.3, "end": 58.1, "title": "short catchy title", "hook": "the opening line of the clip", "reason": "why it works", "score": 85}}]}}

score = 0-100 viral potential. start/end are seconds taken from the transcript.

TRANSCRIPT:
{transcript}
"""


def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


def ask_claude(prompt: str, model: str | None) -> str:
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise RuntimeError("The `claude` CLI was not found on PATH. Install Claude Code or pick another AI.") from None
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {(r.stderr or r.stdout).strip()[-500:]}")
    return r.stdout


def _post_json(url: str, body: dict, headers: dict, timeout: int, what: str) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{what} error {e.code}: {e.read().decode(errors='replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {what} ({e.reason})") from e


def _require_env(name: str, llm: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set (required for the '{llm}' AI)")
    return value


def ask_anthropic(prompt: str, model: str) -> str:
    key = _require_env("ANTHROPIC_API_KEY", "anthropic")
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    data = _post_json(
        f"{base}/v1/messages",
        {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]},
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        600,
        "Anthropic API",
    )
    return "".join(b.get("text", "") for b in data["content"])


def ask_openai(prompt: str, model: str) -> str:
    key = _require_env("OPENAI_API_KEY", "openai")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    data = _post_json(
        f"{base}/chat/completions",
        {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
        {"Authorization": f"Bearer {key}"},
        600,
        "OpenAI API",
    )
    return data["choices"][0]["message"]["content"]


def ask_ollama(prompt: str, model: str) -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if "://" not in host:
        host = f"http://{host}"
    data = _post_json(
        f"{host.rstrip('/')}/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"num_ctx": 32768, "temperature": 0.3},
        },
        {},
        1800,
        "Ollama",
    )
    return data["response"]


def parse_clips(text: str) -> list[dict]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"the AI did not return JSON: {text[:300]!r}")
    data = json.loads(text[start : end + 1])
    clips = []
    for c in data.get("clips", []) if isinstance(data, dict) else []:
        try:
            c = {**c, "start": float(c["start"]), "end": float(c["end"])}
        except (KeyError, TypeError, ValueError):
            continue
        if c["end"] > c["start"]:
            clips.append(c)
    if not clips:
        raise ValueError("the AI returned no usable clips")
    return clips


def snap(clips: list[dict], segments: list[dict], min_d: float, max_d: float) -> list[dict]:
    """Snap start/end to sentence boundaries, then drop clips with an unreasonable length or overlap."""
    starts = [s["start"] for s in segments]
    ends = [s["end"] for s in segments]
    result = []
    for c in clips:
        s = min(starts, key=lambda t: abs(t - float(c["start"])))
        e = min(ends, key=lambda t: abs(t - float(c["end"])))
        if e - s > max_d * 1.3:
            e = max((t for t in ends if t - s <= max_d * 1.3), default=s + max_d)
        if e - s < min_d * 0.6:
            continue
        if any(s < r["end"] and e > r["start"] for r in result):
            continue
        result.append({**c, "start": s, "end": e})
    return sorted(result, key=lambda c: -c.get("score", 0))


def chunk_segments(segments: list[dict], max_chars: int) -> list[list[dict]]:
    """Split a long transcript so each piece fits in the model's context window."""
    chunks, cur, size = [], [], 0
    for seg in segments:
        n = len(seg["text"]) + 16
        if cur and size + n > max_chars:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(seg)
        size += n
    if cur:
        chunks.append(cur)
    return chunks


def _ask_clips(ask, prompt: str, model: str | None) -> list[dict]:
    """Ask the LLM, retrying once if it returns unusable output."""
    last: Exception | None = None
    for _ in range(2):
        try:
            return parse_clips(ask(prompt, model))
        except (ValueError, KeyError) as e:  # json.JSONDecodeError is a ValueError
            last = e
    raise RuntimeError(f"The AI returned an invalid response twice ({last}). Try again or pick a different model.")


def llm_status(llm: str | None = None) -> tuple[bool, str]:
    """Is the chosen AI usable right now? Returns (ok, problem description)."""
    llm = llm or default_llm()
    if llm not in LLMS:
        return False, f"Unknown AI '{llm}'. Choose one of: {', '.join(LLMS)}."
    if llm == "claude" and not shutil.which("claude"):
        return False, "The `claude` CLI was not found on PATH. Pick another AI or install Claude Code."
    for name, var in (("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")):
        if llm == name and not os.environ.get(var):
            return False, f"{var} is not set. Add it to your environment or .env file."
    if llm == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        host = host if "://" in host else f"http://{host}"
        try:
            urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=2).close()
        except Exception:
            return False, f"Ollama is not reachable at {host}. Start it, or set OLLAMA_HOST."
    return True, ""


def find_highlights(
    segments: list[dict],
    title: str,
    n: int,
    min_d: float,
    max_d: float,
    llm: str | None = None,
    model: str | None = None,
) -> list[dict]:
    llm = llm or default_llm()
    if llm not in LLMS:
        raise ValueError(f"Unknown AI '{llm}', choose one of: {', '.join(LLMS)}")
    if not segments:
        raise RuntimeError("No speech was detected in this video, so there is nothing to pick highlights from.")
    model = model or default_llm_model() or DEFAULT_MODELS[llm]
    ask = {"claude": ask_claude, "anthropic": ask_anthropic, "openai": ask_openai, "ollama": ask_ollama}[llm]

    max_chars = int(os.environ.get("AUTOCLIPPER_LLM_MAX_CHARS") or (40_000 if llm == "ollama" else 150_000))
    chunks = chunk_segments(segments, max_chars)
    per_chunk = n if len(chunks) == 1 else -(-n // len(chunks)) + 1
    found: list[dict] = []
    for chunk in chunks:
        prompt = PROMPT.format(
            title=title, n=per_chunk, min_d=int(min_d), max_d=int(max_d), transcript=format_transcript(chunk)
        )
        found += _ask_clips(ask, prompt, model)

    clips = snap(found, segments, min_d, max_d)[:n]
    if not clips:
        raise RuntimeError(
            "The AI did not find any moment that fits the duration limits. Try a wider min/max duration or another model."
        )
    return clips
