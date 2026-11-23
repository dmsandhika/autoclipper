"""Compute a 9:16 crop box that follows the speaker's face."""
import urllib.request
from pathlib import Path
from statistics import median

import cv2

from .config import CACHE

MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
MODEL_PATH = CACHE / "face_detection_yunet_2023mar.onnx"
DETECT_W = 640


def face_detector(w: int, h: int):
    """YuNet face detector (~230KB model, downloaded once). None if the download fails."""
    if not MODEL_PATH.exists():
        try:
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        except Exception as e:
            print(f"  ! Could not download the face detection model, falling back to a center crop: {e}")
            MODEL_PATH.unlink(missing_ok=True)
            return None
    return cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (w, h), 0.7)


def crop_box(video: Path, start: float, end: float, sample_every: float = 1.0) -> tuple[int, int, int, int] | None:
    """Return (w, h, x, y) for the ffmpeg crop filter, or None if the video is already vertical."""
    cap = cv2.VideoCapture(str(video))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cw = int(H * 9 / 16) // 2 * 2
    if cw >= W:
        cap.release()
        return None

    scale = DETECT_W / W
    size = (DETECT_W, int(H * scale))
    detector = face_detector(*size)
    centers = []
    t = start
    while detector and t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        _, faces = detector.detect(cv2.resize(frame, size))
        if faces is not None and len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])[:4]
            centers.append((x + w / 2) / scale)
        t += sample_every
    cap.release()

    cx = median(centers) if centers else W / 2
    x = int(min(max(cx - cw / 2, 0), W - cw))
    return cw, H, x, 0
