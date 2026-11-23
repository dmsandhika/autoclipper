"""Pilih momen terbaik dari transkrip pakai LLM.

Backend: claude (Claude Code CLI), anthropic (API), openai (API kompatibel OpenAI), ollama (lokal).
Konfigurasi lewat env var, lihat .env.example.
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
    """AUTOCLIPPER_LLM kalau di-set; kalau tidak, tebak dari apa yang tersedia."""
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

PROMPT = """Kamu adalah editor video short-form (TikTok/Reels/Shorts) yang ahli membuat konten viral.

Di bawah ini transkrip video berjudul "{title}". Format tiap baris: [detik_mulai-detik_selesai] teks.

Pilih {n} momen terbaik untuk dijadikan klip pendek. Kriteria:
- Durasi tiap klip {min_d}-{max_d} detik.
- Dibuka dengan hook kuat di 3 detik pertama (pertanyaan, pernyataan mengejutkan, opini kontroversial, cerita menarik).
- Bisa dipahami berdiri sendiri tanpa konteks video penuh.
- Berakhir di kalimat yang tuntas, jangan terpotong di tengah kalimat.
- Klip tidak boleh saling tumpang tindih.

Jawab HANYA dengan JSON (tanpa teks lain, tanpa markdown) dengan format:
{{"clips": [{{"start": 12.3, "end": 58.1, "title": "judul singkat menarik", "hook": "kalimat pembuka klip", "reason": "kenapa menarik", "score": 85}}]}}

score = 0-100 potensi viral. start/end pakai detik dari transkrip.

TRANSKRIP:
{transcript}
"""


def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


def ask_claude(prompt: str, model: str | None) -> str:
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI gagal: {r.stderr or r.stdout}")
    return r.stdout


def _post_json(url: str, body: dict, headers: dict, timeout: int, what: str) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{what} error {e.code}: {e.read().decode(errors='replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Tidak bisa menghubungi {what} ({e.reason})") from e


def _require_env(name: str, llm: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} belum diset (dibutuhkan untuk LLM '{llm}')")
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
        raise ValueError(f"LLM tidak mengembalikan JSON:\n{text[:500]}")
    return json.loads(text[start : end + 1])["clips"]


def snap(clips: list[dict], segments: list[dict], min_d: float, max_d: float) -> list[dict]:
    """Rapikan start/end supaya pas di batas kalimat, lalu buang yang durasinya tidak masuk akal."""
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
        raise ValueError(f"LLM '{llm}' tidak dikenal, pilih salah satu: {', '.join(LLMS)}")
    model = model or default_llm_model() or DEFAULT_MODELS[llm]
    prompt = PROMPT.format(
        title=title, n=n, min_d=int(min_d), max_d=int(max_d), transcript=format_transcript(segments)
    )
    ask = {"claude": ask_claude, "anthropic": ask_anthropic, "openai": ask_openai, "ollama": ask_ollama}[llm]
    text = ask(prompt, model)
    return snap(parse_clips(text), segments, min_d, max_d)[:n]
