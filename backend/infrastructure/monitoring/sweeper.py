"""
backend/infrastructure/monitoring/sweeper.py

Background asyncio task that detects and recovers stuck jobs.

A job is "stuck" if it has been in "processing" state for longer than
STUCK_THRESHOLD_SECONDS — which means the worker crashed or timed out without
cleaning up its tracking entry.

Algorithm:
    Every SWEEP_INTERVAL_SECONDS:
        1. ZRANGEBYSCORE voice_os:processing_jobs 0 (now - threshold)
        2. For each stuck job_id → fetch full job from voice_os:job_data:{job_id}
        3a. If retry_count < MAX_RETRIES  → requeue (increments retry_count)
        3b. Else                          → mark failed + push to DLQ

The sorted set is maintained by the worker:
    - ZADD on mark_job_processing()
    - ZREM on clear_job_processing()
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

logger = logging.getLogger("voice_os.sweeper")

SWEEP_INTERVAL_SECONDS = int(os.getenv("SWEEPER_INTERVAL_SECONDS", "30"))
STUCK_THRESHOLD_SECONDS = int(os.getenv("SWEEPER_STUCK_THRESHOLD_SECONDS", "180"))   # 3 min


async def run_sweeper() -> None:
    """
    Intended to run as an asyncio background task inside the API process.
    Does not block the event loop — all Redis calls are wrapped in asyncio.to_thread.
    """
    from backend.infrastructure.queue.redis_queue import (
        MAX_RETRIES,
        get_stuck_jobs,
        push_dead_letter,
        requeue_job,
        set_job_status,
    )
    from backend.infrastructure.monitoring.metrics import increment

    logger.info(
        "Stuck-job sweeper started (interval=%ss, threshold=%ss)",
        SWEEP_INTERVAL_SECONDS, STUCK_THRESHOLD_SECONDS,
    )

    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        try:
            stuck = await asyncio.to_thread(get_stuck_jobs, STUCK_THRESHOLD_SECONDS)
            if not stuck:
                continue

            logger.warning("Sweeper found %d stuck job(s)", len(stuck))
            increment("sweeper_stuck_jobs_detected", float(len(stuck)))

            for job in stuck:
                job_id = job.get("job_id", "unknown")
                retry  = job.get("retry_count", 0)

                if retry < MAX_RETRIES:
                    logger.info(
                        "Sweeper requeueing stuck job %s (retry %s/%s)",
                        job_id, retry + 1, MAX_RETRIES,
                    )
                    await asyncio.to_thread(requeue_job, job)
                    increment("sweeper_jobs_requeued")
                else:
                    logger.error(
                        "Sweeper permanently failing stuck job %s after %s retries",
                        job_id, retry,
                    )
                    await asyncio.to_thread(set_job_status, job_id, "failed")
                    await asyncio.to_thread(
                        push_dead_letter, job, "stuck_in_processing_timeout"
                    )
                    increment("sweeper_jobs_failed")

        except Exception as exc:
            logger.error("Sweeper iteration error: %s", exc, exc_info=True)
