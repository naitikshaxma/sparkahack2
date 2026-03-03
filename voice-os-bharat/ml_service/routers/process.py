import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, Form
from schemas.request import ProcessResponse
from services.whisper_service import transcribe_audio
from services.bert_service import classify_intent
from services.flow_engine import generate_response
from services.tts_service import synthesize_speech

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "audio_output")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/process", response_model=ProcessResponse)
async def process_voice(
    audio: UploadFile = File(...),
    user_id: str = Form(...),
):
    """
    POST /process
    Accepts an audio file + user_id.
    Language is auto-detected by Whisper.
    Returns recognized_text, intent, confidence, response_text, audio_url.
    """
    # Save uploaded audio to temp file
    temp_filename = f"{uuid.uuid4().hex}.webm"
    temp_path = os.path.join(UPLOAD_DIR, temp_filename)

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    try:
        # Step 1: Transcribe audio → text (language auto-detected)
        transcript, detected_language = transcribe_audio(temp_path)

        # Step 2: Classify intent using detected language
        intent, confidence, category = classify_intent(transcript, detected_language)

        # Step 3: Generate deterministic structured response
        # Using Category from classification for flow engine
        response_text = generate_response(intent, category, detected_language)

        # Step 4: Synthesize TTS audio
        tts_filename = f"tts_{uuid.uuid4().hex}.wav"
        tts_path = os.path.join(UPLOAD_DIR, tts_filename)
        synthesize_speech(response_text, detected_language, tts_path)

        # audio_url returns the filename; Express backend will fetch it via http://ml-service:8000/static/audio/{filename}
        return ProcessResponse(
            recognized_text=transcript,
            intent=intent,
            confidence=confidence,
            response_text=response_text,
            audio_url=tts_filename,
        )
    finally:
        # Clean up uploaded audio
        if os.path.exists(temp_path):
            os.remove(temp_path)
