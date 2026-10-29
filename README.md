# AutoClipper

Ubah video YouTube panjang jadi klip vertikal (9:16) lengkap dengan caption otomatis. Semua berjalan lokal dan gratis di Mac Apple Silicon.

**Pipeline:** yt-dlp → mlx-whisper (timestamp per kata) → Claude Code CLI / Ollama (pilih highlight) → OpenCV (crop ikut wajah) → Pillow + ffmpeg (caption & render)

## Setup

```bash
./setup.sh
```

## Pakai

```bash
source .venv/bin/activate
python -m autoclipper "https://www.youtube.com/watch?v=XXXX" --lang id -n 3
```

Hasil ada di `output/<id-video>/`. Lihat semua opsi dengan `python -m autoclipper -h`.
