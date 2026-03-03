from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from routers import process

app = FastAPI(
    title="Voice OS ML Service",
    description="FastAPI ML service for speech-to-text, intent classification, and TTS",
    version="1.0.0",
)

# Serve generated audio files statically
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "audio_output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static/audio", StaticFiles(directory=UPLOAD_DIR), name="static_audio")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(process.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "voice-os-ml-service"}
