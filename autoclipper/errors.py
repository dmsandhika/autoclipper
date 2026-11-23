"""Turn technical exceptions into messages a user can act on."""
import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# (lowercase keywords found in the error, message shown to the user)
_RULES = [
    (("sign in to confirm", "not a bot"),
     "YouTube blocked the download (bot check). Export your browser cookies to a cookies.txt file and set "
     "AUTOCLIPPER_COOKIES, or try again later. See the README."),
    (("private video",), "This video is private."),
    (("video unavailable", "this video is not available", "has been removed"), "This video is unavailable."),
    (("sign in to confirm your age", "age-restricted"), "This video is age-restricted. Provide cookies.txt (see README)."),
    (("unsupported url",), "Unsupported or invalid URL."),
    (("no such file or directory: 'ffmpeg'", "no such file or directory: 'ffprobe'"),
     "ffmpeg is not installed or not on PATH. Install it (e.g. `brew install ffmpeg` or `apt install ffmpeg`)."),
    (("unable to download", "timed out", "temporary failure in name resolution", "connection reset"),
     "Network error while downloading. Check your connection and retry."),
    (("no space left on device",), "The disk is full. Free some space and retry."),
]


def explain(e: BaseException) -> str:
    msg = _ANSI.sub("", str(e)).strip()
    low = msg.lower()
    for keys, text in _RULES:
        if any(k in low for k in keys):
            return text
    if not msg:
        return type(e).__name__
    return msg if len(msg) <= 800 else msg[:800] + "…"
