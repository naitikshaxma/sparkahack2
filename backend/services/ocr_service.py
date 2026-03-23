import json
import time
from typing import Any, Dict
import asyncio

import pytesseract
from openai import OpenAI
from PIL import Image

from ..config import get_settings
from ..logger import log_event


SETTINGS = get_settings()

MODEL_NAME = SETTINGS.openai_chat_model
SYSTEM_PROMPT = (
    "You are an OCR data extractor. Extract structured Aadhaar information from raw OCR text. "
    "Return ONLY valid JSON. If unsure, return null."
)


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=SETTINGS.openai_api_key)
    return _client


def _empty_extraction() -> Dict[str, Any]:
    return {
        "full_name": None,
        "aadhaar_number": None,
        "date_of_birth": None,
        "address": None,
        "confidence": 0.0,
    }


def extract_text(image_path: str, timings: dict | None = None) -> str:
    start = time.perf_counter()
    log_event("ocr_extract_text_start", endpoint="ocr_service", status="success")
    # Requires system-level Tesseract installation and accessible PATH.
    try:
        with Image.open(image_path) as img:
            text = pytesseract.image_to_string(img)
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        if timings is not None:
            timings["ocr_text_extraction_ms"] = elapsed_ms
        log_event("ocr_extract_text_success", endpoint="ocr_service", status="success", response_time_ms=elapsed_ms)
        return text
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        if timings is not None:
            timings["ocr_text_extraction_ms"] = elapsed_ms
        log_event(
            "ocr_extract_text_failure",
            level="error",
            endpoint="ocr_service",
            status="failure",
            error_type=type(exc).__name__,
            response_time_ms=elapsed_ms,
        )
        raise


def extract_structured_data(ocr_text: str, timings: dict | None = None) -> Dict[str, Any]:
    start = time.perf_counter()
    log_event("ocr_structured_data_start", endpoint="ocr_service", status="success", user_input_length=len(ocr_text or ""))
    if not (ocr_text or "").strip():
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        if timings is not None:
            timings["ocr_structuring_ms"] = elapsed_ms
        return _empty_extraction()

    try:
        response = _get_client().chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Extract this OCR text to JSON with keys exactly: "
                        "full_name, aadhaar_number, date_of_birth, address, confidence.\n"
                        f"OCR text:\n{ocr_text}"
                    ),
                },
            ],
            temperature=0,
        )

        parsed = json.loads(response.choices[0].message.content or "{}")
        confidence_raw = parsed.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except (TypeError, ValueError):
            confidence = 0.0

        result = {
            "full_name": parsed.get("full_name"),
            "aadhaar_number": parsed.get("aadhaar_number"),
            "date_of_birth": parsed.get("date_of_birth"),
            "address": parsed.get("address"),
            "confidence": confidence,
        }
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        if timings is not None:
            timings["ocr_structuring_ms"] = elapsed_ms
        log_event("ocr_structured_data_success", endpoint="ocr_service", status="success", response_time_ms=elapsed_ms)
        return result
    except Exception:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        if timings is not None:
            timings["ocr_structuring_ms"] = elapsed_ms
        log_event("ocr_structured_data_failure", level="error", endpoint="ocr_service", status="failure", error_type="OcrStructuringError", response_time_ms=elapsed_ms)
        return _empty_extraction()


class OcrService:
    def extract_text(self, image_path: str, timings: dict | None = None) -> str:
        return extract_text(image_path, timings=timings)

    def extract_structured_data(self, ocr_text: str, timings: dict | None = None) -> Dict[str, Any]:
        return extract_structured_data(ocr_text, timings=timings)

    async def extract_text_async(self, image_path: str, timings: dict | None = None) -> str:
        return await asyncio.to_thread(extract_text, image_path, timings)

    async def extract_structured_data_async(self, ocr_text: str, timings: dict | None = None) -> Dict[str, Any]:
        return await asyncio.to_thread(extract_structured_data, ocr_text, timings)
