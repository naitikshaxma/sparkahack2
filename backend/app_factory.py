import hmac
import hashlib
import os
import time
import uuid
import asyncio

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import clear_current_user_id, decode_access_token, extract_bearer_token, set_current_user_id
from .config import get_settings
from .db import init_db
from .logger import clear_request_context, configure_logging, log_event, log_exception, set_request_context
from .metrics import record_error, record_request
from .routes.auth_routes import router as auth_router
from .routes.intent_routes import router as intent_router
from .routes.response_utils import standardized_error
from .routes.system_routes import router as system_router
from .routes.voice_routes import router as voice_router
from .rag_service import warmup_rag_resources
from .utils.rate_limit import allow_request
from .whisper_service import warmup_whisper


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Voice OS Bharat")
    configure_logging()

    max_concurrent = max(1, int((os.getenv("MAX_CONCURRENT_REQUESTS") or "50").strip() or "50"))
    request_timeout_seconds = max(1.0, float((os.getenv("REQUEST_TIMEOUT_SECONDS") or "30").strip() or "30"))
    concurrency_timeout_seconds = max(0.1, float((os.getenv("CONCURRENCY_ACQUIRE_TIMEOUT_SECONDS") or "1.5").strip() or "1.5"))
    app.state.concurrency_semaphore = asyncio.Semaphore(max_concurrent)
    app.state.request_timeout_seconds = request_timeout_seconds
    app.state.concurrency_timeout_seconds = concurrency_timeout_seconds
    streaming_paths = {
        "/api/process-text-stream",
        "/api/tts-stream",
        "/api/v1/process-text-stream",
        "/api/v1/tts-stream",
    }

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup() -> None:
        settings.validate_runtime()
        try:
            init_db()
        except Exception as exc:
            log_event(
                "database_init_failed",
                level="warning",
                endpoint="startup",
                status="failure",
                error_type=type(exc).__name__,
            )
        warmup_rag = (os.getenv("RAG_WARMUP_ON_STARTUP") or "1").strip().lower() not in {"0", "false", "no", "off"}
        if warmup_rag:
            try:
                warmup_rag_resources(precompute_embeddings=True)
            except Exception as exc:
                log_event(
                    "rag_warmup_failed",
                    level="warning",
                    endpoint="startup",
                    status="failure",
                    error_type=type(exc).__name__,
                )
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
        ip_allowed = allow_request(
            f"ip:{client_ip}",
            max_requests=settings.api_rate_limit_max_requests,
            window_seconds=settings.api_rate_limit_window_seconds,
        )
        if not ip_allowed:
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

        if api_key:
            api_key_id = _api_key_fingerprint(api_key)
            key_allowed = allow_request(
                f"api_key:{api_key_id}",
                max_requests=settings.api_key_rate_limit_max_requests,
                window_seconds=settings.api_rate_limit_window_seconds,
            )
            if not key_allowed:
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

    def _set_security_headers(response) -> None:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none';"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    @app.middleware("http")
    async def api_safety_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_start = time.perf_counter()
        client_ip = _extract_client_ip(request)
        request.state.request_id = request_id
        request.state.timings = {}
        set_request_context(request_id, request.url.path, request.method, "")
        acquired = False
        semaphore_released = False
        is_api = request.url.path.startswith("/api")
        is_streaming = request.url.path in streaming_paths

        token = extract_bearer_token(request.headers.get("authorization", ""))
        authenticated_user_id = ""
        if token:
            try:
                claims = decode_access_token(token, settings.jwt_secret_key, settings.jwt_algorithm)
                authenticated_user_id = str(claims.get("sub") or "").strip()
            except HTTPException:
                authenticated_user_id = ""

        request.state.user_id = authenticated_user_id
        set_request_context(request_id, request.url.path, request.method, authenticated_user_id)
        set_current_user_id(authenticated_user_id)

        requires_jwt = any(request.url.path.startswith(prefix) for prefix in settings.jwt_protected_prefixes)
        if requires_jwt and not authenticated_user_id:
            clear_current_user_id()
            clear_request_context()
            response = JSONResponse(status_code=401, content=standardized_error("Authentication required."), headers={"x-request-id": request_id})
            _set_security_headers(response)
            return response

        log_event(
            "request_start",
            request_id=request_id,
            endpoint=request.url.path,
            status="success",
            client_ip=client_ip,
            method=request.method,
            user_id=authenticated_user_id,
        )

        try:
            _enforce_request_size_limit(request, client_ip, request_id)
            _require_api_key_if_enabled(request)
            _check_rate_limit(request, request_id)
            if is_api and not is_streaming:
                try:
                    await asyncio.wait_for(app.state.concurrency_semaphore.acquire(), timeout=app.state.concurrency_timeout_seconds)
                    acquired = True
                except asyncio.TimeoutError:
                    log_event(
                        "concurrency_limit_reached",
                        level="warning",
                        request_id=request_id,
                        endpoint=request.url.path,
                        status="failure",
                        error_type="concurrency_limit_reached",
                        client_ip=client_ip,
                    )
                    clear_request_context()
                    clear_current_user_id()
                    response = JSONResponse(status_code=429, content=standardized_error("Server busy. Please retry shortly."), headers={"x-request-id": request_id})
                    _set_security_headers(response)
                    return response
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
            clear_current_user_id()
            response = JSONResponse(status_code=exc.status_code, content=standardized_error(str(exc.detail)), headers={"x-request-id": request_id})
            _set_security_headers(response)
            return response

        try:
            if is_api and not is_streaming:
                response = await asyncio.wait_for(call_next(request), timeout=app.state.request_timeout_seconds)
            else:
                response = await call_next(request)
        except asyncio.TimeoutError:
            response_time_ms = round((time.perf_counter() - request_start) * 1000.0, 2)
            record_request(response_time_ms=response_time_ms, success=False)
            record_error("request_timeout")
            log_event(
                "request_timeout",
                level="warning",
                request_id=request_id,
                endpoint=request.url.path,
                status="failure",
                error_type="request_timeout",
                response_time_ms=response_time_ms,
                client_ip=client_ip,
            )
            clear_request_context()
            clear_current_user_id()
            if acquired:
                app.state.concurrency_semaphore.release()
                semaphore_released = True
            response = JSONResponse(status_code=504, content=standardized_error("Request timed out."), headers={"x-request-id": request_id})
            _set_security_headers(response)
            return response
        except Exception:
            if acquired and not semaphore_released:
                app.state.concurrency_semaphore.release()
                semaphore_released = True
            raise
        try:
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
                method=request.method,
                user_id=authenticated_user_id,
            )
            response.headers["x-request-id"] = request_id
            _set_security_headers(response)
            clear_request_context()
            clear_current_user_id()
            return response
        finally:
            if acquired and not semaphore_released:
                app.state.concurrency_semaphore.release()
                semaphore_released = True

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
        response = JSONResponse(status_code=422, content=standardized_error("Invalid request payload.", data={"error_count": len(exc.errors())}))
        _set_security_headers(response)
        clear_request_context()
        clear_current_user_id()
        return response

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
        response = JSONResponse(status_code=exc.status_code, content=standardized_error(str(exc.detail)))
        _set_security_headers(response)
        clear_request_context()
        clear_current_user_id()
        return response

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
        response = JSONResponse(status_code=500, content=standardized_error("Internal server error."))
        _set_security_headers(response)
        clear_request_context()
        clear_current_user_id()
        return response

    # Versioned + legacy compatibility mounts.
    app.include_router(auth_router, prefix="/api")
    app.include_router(auth_router, prefix="/api/v1")

    app.include_router(intent_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")

    app.include_router(intent_router, prefix="/api/v1")
    app.include_router(voice_router, prefix="/api/v1")

    app.include_router(system_router)
    app.include_router(system_router, prefix="/api/v1")

    return app
