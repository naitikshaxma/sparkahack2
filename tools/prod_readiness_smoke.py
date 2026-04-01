import io
import json
import asyncio
import httpx
from backend.main import app

REQUIRED_KEYS = {"success", "type", "message", "data", "confidence"}


def key_report(payload):
    if isinstance(payload, dict):
        keys = set(payload.keys())
        return {
            "present": sorted(list(keys & REQUIRED_KEYS)),
            "missing": sorted(list(REQUIRED_KEYS - keys)),
        }
    return {"present": [], "missing": sorted(list(REQUIRED_KEYS))}


async def run():
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    results = []

    # 1) /api/intent
    r = await client.post("/api/intent", json={"text": "ujjwala yojana kya hai"})
    p = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    results.append({"endpoint": "/api/intent", "status": r.status_code, "body": p, "schema": key_report(p)})

    # 2) /api/process-text
    r = await client.post("/api/process-text", json={"text": "yojana batao", "session_id": "test-session"})
    p = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    results.append({"endpoint": "/api/process-text", "status": r.status_code, "body": p, "schema": key_report(p)})

    # 3) /api/transcribe (minimal wav bytes)
    wav_header = (
        b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"fmt " + (16).to_bytes(4, "little") +
        (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (16000).to_bytes(4, "little") +
        (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little") +
        b"data" + (0).to_bytes(4, "little")
    )
    files = {"audio": ("sample.wav", io.BytesIO(wav_header), "audio/wav")}
    r = await client.post("/api/transcribe", files=files)
    try:
        p = r.json()
    except Exception:
        p = {"raw": r.text}
    results.append({"endpoint": "/api/transcribe", "status": r.status_code, "body": p, "schema": key_report(p)})

    # 4) /api/tts
    r = await client.post("/api/tts", json={"text": "hello", "language": "en"})
    try:
        p = r.json()
    except Exception:
        p = {"raw": r.text}
    results.append({"endpoint": "/api/tts", "status": r.status_code, "body": p, "schema": key_report(p)})

    print(json.dumps(results, ensure_ascii=False, indent=2))
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(run())
