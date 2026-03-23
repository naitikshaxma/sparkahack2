from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_secret_key", re.compile(r"sk-(proj-)?[A-Za-z0-9_-]{20,}")),
    ("github_pat", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "generic_assignment",
        re.compile(
            r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.+=]{12,}"
        ),
    ),
]

ALLOWLIST_FILES = {
    ".env.example",
    "frontend/.env.example",
    "README.md",
}


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _staged_files() -> list[Path]:
    output = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    files = []
    for line in output.splitlines():
        rel = line.strip().replace("\\", "/")
        if not rel:
            continue
        if rel in ALLOWLIST_FILES:
            continue
        files.append(Path(rel))
    return files


def main() -> int:
    try:
        files = _staged_files()
    except Exception as exc:
        print(f"[secret-scan] unable to read staged files: {exc}", file=sys.stderr)
        return 1

    findings: list[str] = []

    for file_path in files:
        if not file_path.exists() or file_path.is_dir():
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for label, pattern in PATTERNS:
            for match in pattern.finditer(content):
                token = match.group(0)

                if "replace-with" in token.lower() or "example" in token.lower():
                    continue

                findings.append(f"{file_path.as_posix()}: {label}: {token[:120]}")

    if findings:
        print("[secret-scan] Potential secrets detected in staged changes:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print("[secret-scan] Commit blocked. Remove secrets or move them to environment variables.", file=sys.stderr)
        return 1

    print("[secret-scan] No potential secrets found in staged files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
