import os
from datetime import datetime

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
TEXT_EXTS = {".txt", ".pdf", ".docx"}

def detect_file_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in TEXT_EXTS:
        return "text"
    return "text"

def get_file_created_at(path: str):
    """
    Windows: getctime usually returns creation time.
    Returns datetime or None.
    """
    try:
        ts = os.path.getctime(path)
        return datetime.fromtimestamp(ts)
    except Exception:
        return None
