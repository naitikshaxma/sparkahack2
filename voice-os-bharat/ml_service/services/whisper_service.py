"""
Whisper Service — Audio → (transcribed text, detected language)
Uses OpenAI Whisper model for speech-to-text transcription with language detection.
"""
from typing import Tuple


def transcribe_audio(audio_path: str, language: str = None) -> Tuple[str, str]:
    """
    Transcribe an audio file to text using Whisper.
    Language is auto-detected when not provided.

    Args:
        audio_path: Path to the audio file
        language: Optional language hint (e.g., 'hi', 'en', 'ta')

    Returns:
        Tuple of (transcribed_text, detected_language_code)
    """
    # TODO: Load and run Whisper model
    # import whisper
    # model = whisper.load_model("base")
    # result = model.transcribe(audio_path, language=language)  # None = auto-detect
    # return result["text"], result["language"]

    # Fallback: return a demo transcript. Use provided language hint or default to 'en'
    detected_language = language or "en"

    fallback_transcripts = {
        "hi": "मेरा खाता बैलेंस बताइए",
        "en": "Check my account balance",
        "mr": "माझ्या खात्यातील शिल्लक सांगा",
        "bn": "আমার অ্যাকাউন্ট ব্যালেন্স জানান",
        "ta": "என் கணக்கு இருப்பை சொல்லுங்கள்",
        "te": "నా ఖాతా బ్యాలెన్స్ చెప్పండి",
        "kn": "ನನ್ನ ಖಾತೆ ಬ್ಯಾಲೆನ್ಸ್ ಹೇಳಿ",
        "ml": "എന്റെ അക്കൗണ്ട് ബാലൻസ് പറയൂ",
        "pa": "ਮੇਰਾ ਖਾਤਾ ਬੈਲੈਂਸ ਦੱਸੋ",
        "gu": "મારું ખાતું બેલેન્સ જણાવો",
    }
    transcript = fallback_transcripts.get(detected_language, fallback_transcripts["en"])
    return transcript, detected_language
