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

## Clip editor

- Drag the yellow handles on the timeline (or use the −/+ buttons) to set start/end.
- Click a word in the transcript to jump to it; double-click to fix a misheard caption word.
- "Save & Render" re-renders the clip. "+ Manual clip" makes a clip from any range.

## Configuration reference

| Variable | Purpose |
|---|---|
| `AUTOCLIPPER_DATA_DIR` | Where `work/` and `output/` live (default: project folder; `/data` in Docker) |
| `AUTOCLIPPER_MODEL_DIR` | Whisper model cache |
| `AUTOCLIPPER_HOST` / `AUTOCLIPPER_PORT` | Web server bind (default `127.0.0.1:8765`) |
| `AUTOCLIPPER_FONT` | Path to a custom caption font (default: bundled Anton) |
| `AUTOCLIPPER_COOKIES` | cookies.txt for yt-dlp |

The web UI has no authentication. Keep it bound to localhost (the compose file does) and do not expose it to the internet.

## License

MIT. The bundled Anton font is under the SIL Open Font License (see `autoclipper/fonts/OFL.txt`).
