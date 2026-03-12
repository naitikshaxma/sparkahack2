import base64
import io
from gtts import gTTS


def generate_tts(text: str, language: str) -> str:
    clean_text = (text or "").strip()
    if not clean_text:
        return ""

    lang = "hi" if (language or "").strip().lower() == "hi" else "en"

    tts = gTTS(text=clean_text, lang=lang)

    fp = io.BytesIO()

    tts.write_to_fp(fp)

    return base64.b64encode(fp.getvalue()).decode("utf-8")
