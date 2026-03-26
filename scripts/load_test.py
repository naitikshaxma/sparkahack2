import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

import httpx


@dataclass
class RequestStat:
    ok: bool
    status_code: int
    latency_ms: float


def _percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * pct)
    return ordered[index]


async def _one_request(client, base_url, session_id, text, language, timeout):
    start = time.perf_counter()
    try:
        response = await client.post(
            f"{base_url}/api/process-text",
            data={"session_id": session_id, "language": language, "text": text},
            timeout=timeout,
        )
        ok = response.status_code == 200
        status_code = response.status_code
    except Exception:
        ok = False
        status_code = 0
    latency_ms = (time.perf_counter() - start) * 1000.0
    return RequestStat(ok=ok, status_code=status_code, latency_ms=latency_ms)


async def run_load(base_url, users, requests_per_user, timeout, text, language):
    limits = httpx.Limits(max_connections=max(200, users * 4), max_keepalive_connections=max(100, users * 2))
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = []
        for user_idx in range(users):
            for req_idx in range(requests_per_user):
                session_id = f"load-user-{user_idx}-req-{req_idx}"
                tasks.append(_one_request(client, base_url, session_id, text, language, timeout))

        started = time.perf_counter()
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - started

    return results, elapsed


def summarize(results, elapsed_seconds):
    total = len(results)
    successes = sum(1 for r in results if r.ok)
    failures = total - successes
    latencies = [r.latency_ms for r in results]
    status_hist = {}
    for item in results:
        status_hist[item.status_code] = status_hist.get(item.status_code, 0) + 1

    print("=== Load Test Summary ===")
    print(f"Total requests: {total}")
    print(f"Successes: {successes}")
    print(f"Failures: {failures}")
    print(f"Failure rate: {(failures / total * 100.0) if total else 0.0:.2f}%")
    print(f"Elapsed time: {elapsed_seconds:.2f}s")
    print(f"Throughput: {(total / elapsed_seconds) if elapsed_seconds > 0 else 0.0:.2f} req/s")

    if latencies:
        print(f"Latency mean: {statistics.mean(latencies):.2f} ms")
        print(f"Latency p50: {_percentile(latencies, 0.50):.2f} ms")
        print(f"Latency p95: {_percentile(latencies, 0.95):.2f} ms")
        print(f"Latency p99: {_percentile(latencies, 0.99):.2f} ms")

    print("Status codes:")
    for code in sorted(status_hist):
        print(f"  {code}: {status_hist[code]}")


def parse_args():
    parser = argparse.ArgumentParser(description="Concurrent load test for /api/process-text")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--users", type=int, default=75, help="Concurrent user count")
    parser.add_argument("--requests-per-user", type=int, default=8, help="Requests issued per user")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    parser.add_argument("--text", default="Need agriculture subsidy details", help="Input text payload")
    parser.add_argument("--language", default="en", help="Language code")
    return parser.parse_args()


async def _main():
    args = parse_args()
    results, elapsed = await run_load(
        base_url=args.base_url,
        users=args.users,
        requests_per_user=args.requests_per_user,
        timeout=args.timeout,
        text=args.text,
        language=args.language,
    )
    summarize(results, elapsed)


if __name__ == "__main__":
    asyncio.run(_main())
