import json
import time
from typing import Any, Dict, List

from backend.services.ml_intent_wrapper import process_user_query
from backend.src.utils.scheme_data import SCHEME_DATA


TURN_QUERIES = [
    "{scheme} kya hai",
    "eligibility kya hai",
    "apply kaise kare",
]


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


def _has_bullets(message: str, min_count: int = 3) -> bool:
    text = str(message or "")
    return text.count("\n-") >= min_count


def _has_numbered_steps(message: str) -> bool:
    text = str(message or "")
    has_dot = all(token in text for token in ["1.", "2.", "3."])
    has_paren = all(token in text for token in ["1)", "2)", "3)"])
    return has_dot or has_paren


def run_smoke() -> Dict[str, Any]:
    schemes = sorted(SCHEME_DATA.keys())
    all_results: List[Dict[str, Any]] = []
    checks_total = 0
    checks_passed = 0
    total_latency = 0.0
    turn_count = 0

    for scheme in schemes:
        ctx: Dict[str, Any] = {"last_scheme": None, "last_intent": None}
        turns: List[Dict[str, Any]] = []

        for index, pattern in enumerate(TURN_QUERIES):
            query = pattern.format(scheme=scheme)
            start = time.perf_counter()
            payload = process_user_query(query, session_context=ctx)
            latency_ms = (time.perf_counter() - start) * 1000.0

            total_latency += latency_ms
            turn_count += 1

            result_type = str(payload.get("type") or "")
            message = str(payload.get("message") or "")
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            detected_scheme = _norm(data.get("scheme") or "")

            if index == 0:
                type_ok = result_type == "scheme_info"
                format_ok = bool(message.strip()) and "\n" in message
                context_ok = detected_scheme == _norm(scheme)
            elif index == 1:
                type_ok = result_type == "eligibility"
                format_ok = _has_bullets(message, min_count=3)
                context_ok = detected_scheme == _norm(scheme)
            else:
                type_ok = result_type == "application_help"
                format_ok = _has_numbered_steps(message)
                context_ok = detected_scheme == _norm(scheme)

            non_empty_ok = bool(message.strip())
            latency_ok = latency_ms < 2000.0

            checks = {
                "type_ok": type_ok,
                "format_ok": format_ok,
                "context_ok": context_ok,
                "non_empty_ok": non_empty_ok,
                "latency_ok": latency_ok,
            }
            checks_total += len(checks)
            checks_passed += sum(1 for value in checks.values() if value)

            turns.append(
                {
                    "turn": index + 1,
                    "query": query,
                    "type": result_type,
                    "message": message,
                    "data_scheme": data.get("scheme"),
                    "context": dict(ctx),
                    "latency_ms": round(latency_ms, 2),
                    "checks": checks,
                }
            )

        all_results.append({"scheme": scheme, "turns": turns})

    accuracy = (checks_passed / checks_total * 100.0) if checks_total else 0.0
    avg_latency = (total_latency / turn_count) if turn_count else 0.0

    failures: List[Dict[str, Any]] = []
    for scheme_result in all_results:
        for turn in scheme_result["turns"]:
            failed = [name for name, ok in turn["checks"].items() if not ok]
            if failed:
                failures.append(
                    {
                        "scheme": scheme_result["scheme"],
                        "turn": turn["turn"],
                        "query": turn["query"],
                        "type": turn["type"],
                        "failed_checks": failed,
                        "latency_ms": turn["latency_ms"],
                    }
                )

    summary = {
        "accuracy": round(accuracy, 2),
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "avg_latency_ms": round(avg_latency, 2),
        "all_schemes_pass": len(failures) == 0,
        "failures": failures,
    }

    return {"summary": summary, "results": all_results}


if __name__ == "__main__":
    report = run_smoke()
    out_path = "tools/smoke_15_orchestration_report.json"
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
