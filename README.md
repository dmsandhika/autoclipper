# AutoClipper

Turn long YouTube videos into vertical (9:16) short clips with auto-generated, word-highlighted captions. Runs on your own machine.

[Bahasa Indonesia](README.id.md)

**Pipeline:** yt-dlp → Whisper (word-level timestamps) → LLM picks highlights → OpenCV face-aware crop → Pillow + ffmpeg (captions & render)

> **Responsible use:** only clip videos you own or have permission to reuse. Downloading from YouTube may violate its Terms of Service, and clips of other people's content may infringe copyright. You are responsible for how you use this tool.

## Quick start (Docker)

```bash
git clone https://github.com/dmsandhika/autoclipper.git && cd autoclipper
cp .env.example .env        # then put your ANTHROPIC_API_KEY in .env
docker compose up
```

Open http://localhost:8765, paste a YouTube link, then preview, edit and download your clips.

Clips and cache live in Docker volumes; Whisper models are downloaded once on first use.

### Choosing the LLM

Set in `.env`:

| `AUTOCLIPPER_LLM` | Needs | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | Default model `claude-haiku-5-5` |
| `openai` | `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL`) | Works with OpenAI-compatible servers |
| `ollama` | `OLLAMA_HOST` | Free and private. `docker compose --profile ollama up`, then `docker compose exec ollama ollama pull qwen2.5:7b` |
| `claude` | `claude` CLI on PATH | Native install only |

Override the model with `AUTOCLIPPER_LLM_MODEL`.

### Transcription

| Variable | Default | |
|---|---|---|
| `AUTOCLIPPER_WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3`. Bigger is slower and more accurate. |
| `AUTOCLIPPER_DEVICE` | `auto` | `cpu` or `cuda` |

Docker runs on CPU, so transcription is slower than native. On Apple Silicon, run natively to use MLX (below).

### YouTube blocks the download?

Datacenter and some home IPs get "Sign in to confirm you're not a bot". Export your cookies to `cookies.txt` (browser extension), mount it in `docker-compose.yml`, and set `AUTOCLIPPER_COOKIES=/run/cookies.txt`.

## Native install

Requires Python 3.10+ and ffmpeg.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # macOS Apple Silicon gets mlx-whisper, others get faster-whisper
cp .env.example .env              # or export the variables yourself
python -m autoclipper.web         # web UI at http://127.0.0.1:8765
```

On macOS, `./setup.sh` does all of this (uses Homebrew and uv).

CLI:

```bash
python -m autoclipper "https://www.youtube.com/watch?v=XXXX" --lang en -n 3
```

Results go to `output/<video-id>/`. See `python -m autoclipper -h` for all options.

## Web UI

- Setup status panel: shows which AI and Whisper backend are active and tells you what is missing (API key, ffmpeg, Ollama not running) *before* you start a long job.
- Live progress per stage, **Retry** on failures, **Delete project** to free disk space, **Download all** as a zip.
- Interface in English or Indonesian (switch at the bottom of the sidebar); follows light/dark mode.

### Clip editor

- Drag the yellow handles on the timeline (or use −/+) to set start/end.
- Shortcuts: `Space` play/pause, `I` / `O` set start/end at the playhead, `←` `→` seek (Shift = fine).
- Click a word in the transcript to jump to it; double-click to fix a misheard caption word.
- "Save & render" re-renders the clip. "+ Manual clip" makes a clip from any range.

## Configuration reference

| Variable | Purpose |
|---|---|
| `AUTOCLIPPER_DATA_DIR` | Where `work/` and `output/` live (default: project folder; `/data` in Docker) |
| `AUTOCLIPPER_MODEL_DIR` | Whisper model cache |
| `AUTOCLIPPER_HOST` / `AUTOCLIPPER_PORT` | Web server bind (default `127.0.0.1:8765`) |
| `AUTOCLIPPER_FONT` | Path to a custom caption font (default: bundled Anton) |
| `AUTOCLIPPER_COOKIES` | cookies.txt for yt-dlp |
| `AUTOCLIPPER_PASSWORD` | Enables HTTP Basic auth for the web UI (any username) |
| `AUTOCLIPPER_ALLOW_LOCAL` | `1` lets the web UI process local file paths (always on when bound to localhost) |
| `AUTOCLIPPER_LLM_MAX_CHARS` | Max transcript characters per LLM request; longer videos are split automatically |

### Security notes

- By default the server binds to `127.0.0.1` and the compose file only publishes the port on localhost.
- If you expose it to a network, set `AUTOCLIPPER_PASSWORD` and put it behind HTTPS (a reverse proxy). Local file paths and non-http(s) sources are rejected when the server is not bound to localhost.
- API keys are read from the environment only. They are never sent to the browser or written to logs.

### Limitations

- The bundled caption font (Anton) covers Latin scripts. For other scripts (Japanese, Arabic, ...) set `AUTOCLIPPER_FONT` to a font that has those glyphs.
- One job is processed at a time; others wait in the queue. Running jobs cannot be cancelled yet.
- Face-aware cropping follows the main speaker; videos with several people at once are centered on the median face position.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q tests
```

## License

MIT. The bundled Anton font is under the SIL Open Font License (see `autoclipper/fonts/OFL.txt`).
