from __future__ import annotations

from ...utils import rate_limit as legacy_rate_limit


def allow_request(key: str, *, max_requests: int, window_seconds: int) -> bool:
    return legacy_rate_limit.allow_request(
        key,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
