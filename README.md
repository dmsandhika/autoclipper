# AutoClipper

Ubah video YouTube panjang jadi klip vertikal (9:16) lengkap dengan caption otomatis. Semua berjalan lokal dan gratis di Mac Apple Silicon.

**Pipeline:** yt-dlp → mlx-whisper (timestamp per kata) → Claude Code CLI / Ollama (pilih highlight) → OpenCV (crop ikut wajah) → Pillow + ffmpeg (caption & render)

## Setup

```bash
./setup.sh
```

## Pakai lewat web (disarankan)

```bash
source .venv/bin/activate
python -m autoclipper.web
```

Browser akan terbuka di http://127.0.0.1:8765. Paste link YouTube, tunggu prosesnya, lalu preview, edit, dan download klip.

Editor klip:
- Geser handle kuning di timeline (atau pakai tombol −/+) untuk mengatur start/end.
- Klik kata di transkrip untuk lompat ke waktunya. Klik dua kali untuk memperbaiki kata caption yang salah dengar.
- "Simpan & Render" untuk me-render ulang klip.
- "+ Klip manual" untuk membuat klip dari bagian mana pun.

## Pakai lewat CLI

```bash
source .venv/bin/activate
python -m autoclipper "https://www.youtube.com/watch?v=XXXX" --lang id -n 3
```

Hasil ada di `output/<id-video>/`. Lihat semua opsi dengan `python -m autoclipper -h`.
