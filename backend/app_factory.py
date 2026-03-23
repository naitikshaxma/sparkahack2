import hmac
import hashlib
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .logger import clear_request_context, configure_logging, log_event, log_exception, set_request_context
from .metrics import record_error, record_request
from .routes.intent_routes import router as intent_router
from .routes.response_utils import standardized_error
from .routes.system_routes import router as system_router
from .routes.voice_routes import router as voice_router
from .whisper_service import warmup_whisper


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Voice OS Bharat")
    configure_logging()

    _rate_limit_lock = threading.Lock()
    _ip_rate_limit_buckets: dict[str, list[float]] = {}
    _api_key_rate_limit_buckets: dict[str, list[float]] = {}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup() -> None:
        settings.validate_runtime()
        warmup_whisper()

    def _extract_client_ip(request: Request) -> str:
        if settings.trust_proxy_headers:
            forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
            if forwarded_for:
                first_ip = forwarded_for.split(",", 1)[0].strip()
                if first_ip:
                    return first_ip

            real_ip = (request.headers.get("x-real-ip") or "").strip()
            if real_ip:
                return real_ip

        return request.client.host if request.client else "unknown"

    def _extract_api_key(request: Request) -> str:
        header_key = (request.headers.get("x-api-key") or "").strip()
        if header_key:
            return header_key

        authorization = (request.headers.get("authorization") or "").strip()
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return ""

    def _api_key_fingerprint(api_key: str) -> str:
        if not api_key:
            return ""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]

    def _enforce_request_size_limit(request: Request, client_ip: str, request_id: str) -> None:
        if not request.url.path.startswith("/api"):
            return

        content_length = request.headers.get("content-length")
        if not content_length:
            return

        try:
            size_bytes = int(content_length)
        except ValueError:
            return

        if size_bytes > settings.max_request_size_bytes:
            log_event(
                "security_request_rejected",
                level="warning",
                request_id=request_id,
                endpoint=request.url.path,
                status="failure",
                error_type="request_size_limit_exceeded",
                client_ip=client_ip,
                size_bytes=size_bytes,
                max_request_size_bytes=settings.max_request_size_bytes,
            )
            raise HTTPException(status_code=413, detail="Request payload too large.")

    def _require_api_key_if_enabled(request: Request) -> None:
        if not request.url.path.startswith("/api"):
            return
        if not settings.enable_api_key_auth:
            return

        provided_key = _extract_api_key(request)
        if not provided_key:
            raise HTTPException(status_code=401, detail="Missing API key.")
        if not hmac.compare_digest(provided_key, settings.api_auth_key):
            raise HTTPException(status_code=403, detail="Invalid API key.")

    def _check_rate_limit(request: Request, request_id: str) -> None:
        if not request.url.path.startswith("/api"):
            return

        client_ip = _extract_client_ip(request)
        api_key = _extract_api_key(request)
        now = time.time()
        with _rate_limit_lock:
            bucket = _ip_rate_limit_buckets.get(client_ip, [])
            cutoff = now - settings.api_rate_limit_window_seconds
            bucket = [timestamp for timestamp in bucket if timestamp >= cutoff]
            if len(bucket) >= settings.api_rate_limit_max_requests:
                log_event(
                    "security_request_rejected",
                    level="warning",
                    request_id=request_id,
                    endpoint=request.url.path,
                    status="failure",
                    error_type="ip_rate_limit_exceeded",
                    client_ip=client_ip,
                )
                raise HTTPException(status_code=429, detail="Too many requests. Please retry later.")
            bucket.append(now)
            _ip_rate_limit_buckets[client_ip] = bucket

            if api_key:
                api_key_id = _api_key_fingerprint(api_key)
                key_bucket = _api_key_rate_limit_buckets.get(api_key_id, [])
                key_bucket = [timestamp for timestamp in key_bucket if timestamp >= cutoff]
                if len(key_bucket) >= settings.api_key_rate_limit_max_requests:
                    log_event(
                        "security_request_rejected",
                        level="warning",
                        request_id=request_id,
                        endpoint=request.url.path,
                        status="failure",
                        error_type="api_key_rate_limit_exceeded",
                        client_ip=client_ip,
                        api_key_id=api_key_id,
                    )
                    raise HTTPException(status_code=429, detail="Too many requests. Please retry later.")
                key_bucket.append(now)
                _api_key_rate_limit_buckets[api_key_id] = key_bucket

    @app.middleware("http")
    async def api_safety_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_start = time.perf_counter()
        client_ip = _extract_client_ip(request)
        request.state.request_id = request_id
        request.state.timings = {}
        set_request_context(request_id, request.url.path)

        log_event(
            "request_start",
            request_id=request_id,
            endpoint=request.url.path,
            status="success",
            client_ip=client_ip,
            method=request.method,
        )

        try:
            _enforce_request_size_limit(request, client_ip, request_id)
            _require_api_key_if_enabled(request)
            _check_rate_limit(request, request_id)
        except HTTPException as exc:
            response_time_ms = round((time.perf_counter() - request_start) * 1000.0, 2)
            record_request(response_time_ms=response_time_ms, success=False)
            record_error(type(exc).__name__)
            log_event(
                "middleware_policy_rejection",
                level="warning",
                request_id=request_id,
                endpoint=request.url.path,
                status="failure",
                error_type=type(exc).__name__,
                response_time_ms=response_time_ms,
                client_ip=client_ip,
                status_code=exc.status_code,
            )
            clear_request_context()
            return JSONResponse(status_code=exc.status_code, content=standardized_error(str(exc.detail)), headers={"x-request-id": request_id})

        response = await call_next(request)
        response_time_ms = round((time.perf_counter() - request_start) * 1000.0, 2)
        status = "success" if response.status_code < 400 else "failure"
        record_request(response_time_ms=response_time_ms, success=(status == "success"))
        if status == "failure":
            record_error(f"http_{response.status_code}")
        log_event(
            "request_complete",
            request_id=request_id,
            endpoint=request.url.path,
            status=status,
            error_type=None if status == "success" else f"http_{response.status_code}",
            intent=getattr(request.state, "intent", None),
            confidence=getattr(request.state, "confidence", None),
            user_input_length=getattr(request.state, "user_input_length", None),
            response_time_ms=response_time_ms,
            timings=getattr(request.state, "timings", {}),
            status_code=response.status_code,
        )
        response.headers["x-request-id"] = request_id
        clear_request_context()
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        record_error(type(exc).__name__)
        log_event(
            "request_validation_error",
            level="warning",
            request_id=getattr(request.state, "request_id", ""),
            endpoint=request.url.path,
            status="failure",
            error_type=type(exc).__name__,
            user_input_length=getattr(request.state, "user_input_length", None),
        )
        return JSONResponse(status_code=422, content=standardized_error("Invalid request payload.", data={"error_count": len(exc.errors())}))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        record_error(type(exc).__name__)
        log_event(
            "http_exception",
            level="warning",
            request_id=getattr(request.state, "request_id", ""),
            endpoint=request.url.path,
            status="failure",
            error_type=type(exc).__name__,
            status_code=exc.status_code,
        )
        return JSONResponse(status_code=exc.status_code, content=standardized_error(str(exc.detail)))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        record_error(type(exc).__name__)
        log_exception(
            exc,
            request_id=getattr(request.state, "request_id", ""),
            endpoint=request.url.path,
            safe_context={
                "method": request.method,
                "client_ip": _extract_client_ip(request),
                "user_input_length": getattr(request.state, "user_input_length", None),
            },
        )
        return JSONResponse(status_code=500, content=standardized_error("Internal server error."))

    # Versioned + legacy compatibility mounts.
    app.include_router(intent_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")

    app.include_router(intent_router, prefix="/api/v1")
    app.include_router(voice_router, prefix="/api/v1")

    app.include_router(system_router)
    app.include_router(system_router, prefix="/api/v1")

    return app
