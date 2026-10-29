"""Tentukan area crop 9:16 yang mengikuti wajah pembicara."""
from pathlib import Path
from statistics import median

import cv2


def crop_box(video: Path, start: float, end: float, sample_every: float = 1.0) -> tuple[int, int, int, int] | None:
    """Return (w, h, x, y) untuk filter crop ffmpeg, atau None kalau video sudah vertikal."""
    cap = cv2.VideoCapture(str(video))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cw = int(H * 9 / 16) // 2 * 2
    if cw >= W:
        cap.release()
        return None

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    scale = 640 / W
    centers = []
    t = start
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, None, fx=scale, fy=scale)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(30, 30))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            centers.append((x + w / 2) / scale)
        t += sample_every
    cap.release()

    cx = median(centers) if centers else W / 2
    x = int(min(max(cx - cw / 2, 0), W - cw))
    return cw, H, x, 0
