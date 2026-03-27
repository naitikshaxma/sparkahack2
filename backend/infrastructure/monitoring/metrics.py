"""
backend/infrastructure/monitoring/metrics.py

Cross-process metrics collector backed by Redis (falls back to in-process dicts).

Usage (from worker OR from API):
    from backend.infrastructure.monitoring.metrics import record_latency, increment

    increment("jobs_processed_total")
    record_latency("stt", 234.5)

Expose at /api/v1/sys/metrics in Prometheus text format.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

# ── In-process fallback (single-process dev / no Redis) ─────────────────────────
_lock = threading.Lock()
_mem_counters: Dict[str, float] = {}
_mem_latency: Dict[str, Dict[str, float]] = {}   # stage → {count, sum_ms, ema}

_EMA_ALPHA = 0.1   # smoothing factor for exponential moving average

# ── Redis key schema ─────────────────────────────────────────────────────────────
METRICS_COUNTERS_KEY = "voice_os:metrics:counters"        # HASH  name→value
METRICS_LATENCY_KEY  = "voice_os:metrics:lat:{stage}"     # HASH  count, sum, ema


def _get_redis() -> Optional[Any]:
    try:
        from backend.infrastructure.queue.redis_queue import _get_redis as _qr
        return _qr()
    except Exception:
        return None


# ── Counter ──────────────────────────────────────────────────────────────────────
def increment(name: str, value: float = 1.0) -> None:
    """Increment a named counter (e.g. 'jobs_processed_total', 'jobs_failed_total')."""
    r = _get_redis()
    if r is not None:
        try:
            r.hincrbyfloat(METRICS_COUNTERS_KEY, name, value)
            return
        except Exception:
            pass
    with _lock:
        _mem_counters[name] = _mem_counters.get(name, 0.0) + value


def get_counter(name: str) -> float:
    r = _get_redis()
    if r is not None:
        try:
            val = r.hget(METRICS_COUNTERS_KEY, name)
            return float(val) if val else 0.0
        except Exception:
            pass
    with _lock:
        return _mem_counters.get(name, 0.0)


def get_all_counters() -> Dict[str, float]:
    r = _get_redis()
    if r is not None:
        try:
            raw = r.hgetall(METRICS_COUNTERS_KEY)
            return {k: float(v) for k, v in raw.items()}
        except Exception:
            pass
    with _lock:
        return dict(_mem_counters)


# ── Latency (EMA + running average) ─────────────────────────────────────────────
def record_latency(stage: str, duration_ms: float) -> None:
    """
    Record a latency sample for a named stage (stt, intent+rag, tts).
    Maintains count, cumulative sum (for true average), and EMA.
    """
    r = _get_redis()
    key = METRICS_LATENCY_KEY.format(stage=stage)
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.hincrbyfloat(key, "count", 1)
            pipe.hincrbyfloat(key, "sum_ms", duration_ms)
            # EMA: read current, compute new
            results = r.hmget(key, "ema")
            current_ema = float(results[0]) if results[0] else duration_ms
            new_ema = (1 - _EMA_ALPHA) * current_ema + _EMA_ALPHA * duration_ms
            pipe.hset(key, "ema", new_ema)
            r.expire(key, 86400)   # 24h TTL on metric keys
            pipe.execute()
            return
        except Exception:
            pass
    with _lock:
        entry = _mem_latency.setdefault(stage, {"count": 0.0, "sum_ms": 0.0, "ema": duration_ms})
        entry["count"] += 1
        entry["sum_ms"] += duration_ms
        entry["ema"] = (1 - _EMA_ALPHA) * entry["ema"] + _EMA_ALPHA * duration_ms


def get_latency_stats(stage: str) -> Dict[str, float]:
    """Return {count, avg_ms, ema_ms} for a stage."""
    r = _get_redis()
    key = METRICS_LATENCY_KEY.format(stage=stage)
    if r is not None:
        try:
            raw = r.hgetall(key)
            if raw:
                count  = float(raw.get("count", 0))
                sum_ms = float(raw.get("sum_ms", 0))
                ema    = float(raw.get("ema", 0))
                return {
                    "count":  count,
                    "avg_ms": sum_ms / count if count else 0.0,
                    "ema_ms": ema,
                }
        except Exception:
            pass
    with _lock:
        entry = _mem_latency.get(stage, {})
        count  = entry.get("count", 0.0)
        sum_ms = entry.get("sum_ms", 0.0)
        return {
            "count":  count,
            "avg_ms": sum_ms / count if count else 0.0,
            "ema_ms": entry.get("ema", 0.0),
        }


# ── Prometheus text format ────────────────────────────────────────────────────────
def prometheus_text() -> str:
    """
    Render all metrics as Prometheus text exposition format.
    Suitable for scraping by Prometheus, Grafana, or any compatible tool.
    """
    from backend.infrastructure.queue.redis_queue import queue_length, dead_letter_length

    lines: list[str] = []

    def gauge(name: str, value: float, help_text: str) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value:.4g}")

    def counter(name: str, value: float, help_text: str) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name}_total {value:.4g}")

    # ── Queue health ──────────────────────────────────────────────────────────
    gauge("voice_os_queue_length",       float(queue_length()),       "Current job queue depth")
    gauge("voice_os_dead_letter_length", float(dead_letter_length()), "Dead letter queue depth")

    # ── Job counters ──────────────────────────────────────────────────────────
    counters = get_all_counters()
    for name, value in counters.items():
        clean = name.replace("-", "_").replace(".", "_")
        counter(f"voice_os_{clean}", value, f"voice_os {name}")

    # ── Stage latencies ───────────────────────────────────────────────────────
    for stage in ("stt", "intent+rag", "tts"):
        safe = stage.replace("+", "_")
        stats = get_latency_stats(stage)
        if stats["count"] > 0:
            lines.append(f"# HELP voice_os_latency_{safe}_avg_ms Average {stage} latency ms (true mean)")
            lines.append(f"# TYPE voice_os_latency_{safe}_avg_ms gauge")
            lines.append(f"voice_os_latency_{safe}_avg_ms {stats['avg_ms']:.2f}")

            lines.append(f"# HELP voice_os_latency_{safe}_ema_ms Exponential moving avg {stage} latency ms")
            lines.append(f"# TYPE voice_os_latency_{safe}_ema_ms gauge")
            lines.append(f"voice_os_latency_{safe}_ema_ms {stats['ema_ms']:.2f}")

    lines.append("")   # Prometheus requires trailing newline
    return "\n".join(lines)
