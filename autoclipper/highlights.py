"""Pilih momen terbaik dari transkrip pakai LLM (Claude Code CLI atau Ollama lokal)."""
import json
import subprocess
import urllib.request

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


def ask_ollama(prompt: str, model: str) -> str:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": 32768, "temperature": 0.3},
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as resp:
        return json.loads(resp.read())["response"]


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
    llm: str = "claude",
    model: str | None = None,
) -> list[dict]:
    prompt = PROMPT.format(
        title=title, n=n, min_d=int(min_d), max_d=int(max_d), transcript=format_transcript(segments)
    )
    text = ask_claude(prompt, model) if llm == "claude" else ask_ollama(prompt, model or "qwen2.5:7b")
    return snap(parse_clips(text), segments, min_d, max_d)[:n]
