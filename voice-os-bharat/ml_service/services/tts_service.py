"""
TTS Service — response_text → .wav audio file
Converts response text to speech audio.
"""


def synthesize_speech(text: str, language: str, output_path: str) -> None:
    """
    Convert text to speech and save as .wav file.

    Args:
        text: Response text to synthesize
        language: Language code
        output_path: Path to save the .wav file
    """
    # TODO: Implement real TTS using gTTS, pyttsx3, or a neural TTS model
    # from gtts import gTTS
    # tts = gTTS(text=text, lang=language)
    # tts.save(output_path)

    # Placeholder: create an empty wav file
    import wave
    import struct

    # Generate a short silent wav file as placeholder
    sample_rate = 16000
    duration = 0.5  # seconds
    num_samples = int(sample_rate * duration)

    with wave.open(output_path, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for _ in range(num_samples):
            wav_file.writeframes(struct.pack("<h", 0))
