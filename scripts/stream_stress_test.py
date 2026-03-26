import argparse
import concurrent.futures
import random
import time
from typing import Tuple

import requests


def _run_stream(base_url: str, session_id: str, text: str, interrupt_rate: float) -> Tuple[bool, str]:
    try:
        response = requests.post(
            f"{base_url}/api/process-text-stream",
            data={"text": text, "session_id": session_id, "language": "en"},
            timeout=60,
            stream=True,
        )
        response.raise_for_status()

        interrupted = False
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, (bytes, bytearray)) else str(raw_line)
            if '"type": "audio_chunk"' in line and random.random() < interrupt_rate:
                requests.post(
                    f"{base_url}/api/tts-interrupt",
                    data={"session_id": session_id},
                    timeout=10,
                )
                interrupted = True
            if '"type": "done"' in line:
                break

        return True, "interrupted" if interrupted else "completed"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress test streaming endpoint")
    parser.add_argument("--base-url", default="http://127.0.0.1:8099")
    parser.add_argument("--users", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--interrupt-rate", type=float, default=0.3)
    parser.add_argument("--text", default="Need information about PM Kisan scheme")
    args = parser.parse_args()

    total = args.users * args.iterations
    successes = 0
    failures = 0

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as executor:
        futures = []
        for user_index in range(args.users):
            session_id = f"stress-{user_index}-{int(start)}"
            for _ in range(args.iterations):
                futures.append(
                    executor.submit(
                        _run_stream,
                        args.base_url,
                        session_id,
                        args.text,
                        max(0.0, min(1.0, args.interrupt_rate)),
                    )
                )

        for future in concurrent.futures.as_completed(futures):
            ok, detail = future.result()
            if ok:
                successes += 1
            else:
                failures += 1
                print(f"FAIL: {detail}")

    elapsed = time.time() - start
    print(f"STRESS_TEST_DONE total={total} ok={successes} failed={failures} elapsed_s={elapsed:.2f}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
