import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import whisper

try:
    import imageio_ffmpeg  # type: ignore
except Exception:
    imageio_ffmpeg = None

if shutil.which("ffmpeg") is None and imageio_ffmpeg is not None:
    bundled_ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    ffmpeg_alias = bundled_ffmpeg_path.with_name("ffmpeg.exe")
    if not ffmpeg_alias.exists():
        try:
            shutil.copy2(bundled_ffmpeg_path, ffmpeg_alias)
        except Exception:
            ffmpeg_alias = bundled_ffmpeg_path

    bundled_dir = str(ffmpeg_alias.parent)
    os.environ["PATH"] = f"{bundled_dir}{os.pathsep}{os.environ.get('PATH', '')}"

WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_SIZE", "base")
FORCED_TRANSCRIBE_LANGUAGE = "hi"
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
_model = None


def _normalize_suffix(source_suffix: Optional[str]) -> str:
    suffix = (source_suffix or ".webm").strip()
    if not suffix:
        return ".webm"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix


def warmup_whisper() -> None:
    _get_model()


def _get_model():
    global _model
    if _model is None:
        print(f"Loading Whisper STT model: {WHISPER_MODEL_NAME}")
        _model = whisper.load_model(WHISPER_MODEL_NAME)
    return _model


def get_whisper_status() -> dict:
    return {
        "model_name": WHISPER_MODEL_NAME,
        "model_loaded": _model is not None,
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "forced_language": FORCED_TRANSCRIBE_LANGUAGE,
    }


def transcribe_audio(audio_bytes: bytes, language: Optional[str] = None, source_suffix: str = ".webm") -> str:
    """
    Transcribe audio bytes using Whisper.
    """
    if not audio_bytes:
        return ""
    if not FFMPEG_AVAILABLE:
        raise RuntimeError("ffmpeg is not available in PATH; Whisper transcription requires ffmpeg.")

    suffix = _normalize_suffix(source_suffix)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        # Hindi-first mode to prevent Urdu-script drift for Hindi speech input.
        _ = language
        options = {"fp16": False, "language": FORCED_TRANSCRIBE_LANGUAGE}
        result = _get_model().transcribe(tmp_path, **options)
        transcript = result.get("text", "").strip()
        return transcript
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
