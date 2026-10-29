"""Caption gaya TikTok: 3 kata per layar, kata yang sedang diucapkan di-highlight.

Caption dirender jadi PNG transparan + daftar concat ffmpeg (tidak butuh libass).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 420
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
WHITE = (255, 255, 255, 255)
HIGHLIGHT = (255, 221, 0, 255)
STROKE = (0, 0, 0, 255)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def clip_words(segments: list[dict], start: float, end: float) -> list[dict]:
    """Ambil kata-kata dalam rentang klip, timestamp dijadikan relatif ke awal klip."""
    words = [
        {"word": w["word"], "start": max(w["start"] - start, 0), "end": min(w["end"], end) - start}
        for s in segments
        for w in s["words"]
        if w["start"] >= start - 0.05 and w["end"] <= end + 0.3
    ]
    # Tahan tiap kata sampai kata berikutnya muncul supaya caption tidak berkedip
    for cur, nxt in zip(words, words[1:]):
        if nxt["start"] - cur["end"] < 0.6:
            cur["end"] = nxt["start"]
    return words


def pages(words: list[dict], per_page: int = 3) -> list[list[dict]]:
    result, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == per_page or w["word"][-1:] in ".?!,":
            result.append(cur)
            cur = []
    if cur:
        result.append(cur)
    return result


def layout(texts: list[str], font: ImageFont.FreeTypeFont, max_w: int) -> list[list[int]]:
    """Bagi kata ke baris-baris (index kata) supaya tidak melebihi lebar."""
    space = font.getlength(" ")
    lines, cur, cur_w = [], [], 0.0
    for i, t in enumerate(texts):
        w = font.getlength(t)
        if cur and cur_w + space + w > max_w:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur_w += (space if cur else 0) + w
        cur.append(i)
    if cur:
        lines.append(cur)
    return lines


def render_page(page: list[dict], active: int, font: ImageFont.FreeTypeFont) -> Image.Image:
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    texts = [w["word"].upper() for w in page]
    lines = layout(texts, font, WIDTH - 120)
    line_h = font.size * 1.2
    space = font.getlength(" ")
    y = (HEIGHT - line_h * len(lines)) / 2
    for line in lines:
        line_w = sum(font.getlength(texts[i]) for i in line) + space * (len(line) - 1)
        x = (WIDTH - line_w) / 2
        for i in line:
            color = HIGHLIGHT if i == active else WHITE
            draw.text((x, y), texts[i], font=font, fill=color, stroke_width=8, stroke_fill=STROKE)
            x += font.getlength(texts[i]) + space
        y += line_h
    return img


def build(segments: list[dict], start: float, end: float, out_dir: Path, font_size: int = 88) -> Path:
    """Render frame caption dan return path ke file concat ffmpeg."""
    out_dir.mkdir(parents=True, exist_ok=True)
    font = load_font(font_size)
    duration = end - start

    blank = out_dir / "blank.png"
    Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)).save(blank)

    entries: list[tuple[Path, float]] = []
    t = 0.0
    n = 0
    for page in pages(clip_words(segments, start, end)):
        for i, w in enumerate(page):
            if w["start"] > t:
                entries.append((blank, w["start"] - t))
                t = w["start"]
            w_end = min(w["end"], duration)
            if w_end <= t:
                continue
            path = out_dir / f"c{n:04d}.png"
            render_page(page, i, font).save(path)
            n += 1
            entries.append((path, w_end - t))
            t = w_end
    if t < duration:
        entries.append((blank, duration - t))

    concat = out_dir / "captions.txt"
    lines = []
    for path, dur in entries:
        lines += [f"file '{path.resolve()}'", f"duration {dur:.3f}"]
    lines.append(f"file '{entries[-1][0].resolve()}'")  # concat demuxer butuh entry terakhir diulang
    concat.write_text("\n".join(lines) + "\n")
    return concat
