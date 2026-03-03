from pydantic import BaseModel
from typing import Optional


class ProcessResponse(BaseModel):
    """Output schema for the /process endpoint — matches spec exactly."""
    recognized_text: str
    intent: str
    confidence: float
    response_text: str
    audio_url: Optional[str] = None
