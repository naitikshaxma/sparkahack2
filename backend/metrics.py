from __future__ import annotations

import threading
import time
from typing import Any, Dict


_LOCK = threading.Lock()
_START_TIME = time.time()
_TOTAL_REQUESTS = 0
_SUCCESS_REQUESTS = 0
_FAILURE_REQUESTS = 0
_TOTAL_LATENCY_MS = 0.0
_ERROR_TYPES: dict[str, int] = {}
_FALLBACK_FREQUENCY = 0


def record_request(*, response_time_ms: float, success: bool) -> None:
    global _TOTAL_REQUESTS, _SUCCESS_REQUESTS, _FAILURE_REQUESTS, _TOTAL_LATENCY_MS
    with _LOCK:
        _TOTAL_REQUESTS += 1
        _TOTAL_LATENCY_MS += max(0.0, float(response_time_ms))
        if success:
            _SUCCESS_REQUESTS += 1
        else:
            _FAILURE_REQUESTS += 1


def record_error(error_type: str) -> None:
    key = (error_type or "unknown_error").strip() or "unknown_error"
    with _LOCK:
        _ERROR_TYPES[key] = int(_ERROR_TYPES.get(key, 0)) + 1


def record_fallback() -> None:
    global _FALLBACK_FREQUENCY
    with _LOCK:
        _FALLBACK_FREQUENCY += 1


def get_metrics_snapshot() -> Dict[str, Any]:
    with _LOCK:
        total_requests = _TOTAL_REQUESTS
        success_requests = _SUCCESS_REQUESTS
        failure_requests = _FAILURE_REQUESTS
        total_latency_ms = _TOTAL_LATENCY_MS
        average_latency_ms = (total_latency_ms / total_requests) if total_requests else 0.0
        success_rate = (success_requests / total_requests) if total_requests else 0.0
        failure_rate = (failure_requests / total_requests) if total_requests else 0.0

        return {
            "uptime_seconds": max(0, int(time.time() - _START_TIME)),
            "total_requests": total_requests,
            "success_requests": success_requests,
            "failure_requests": failure_requests,
            "success_rate": round(success_rate, 4),
            "failure_rate": round(failure_rate, 4),
            "error_rate": round(failure_rate, 4),
            "average_latency_ms": round(average_latency_ms, 2),
            "fallback_frequency": int(_FALLBACK_FREQUENCY),
            "error_types": dict(_ERROR_TYPES),
        }
