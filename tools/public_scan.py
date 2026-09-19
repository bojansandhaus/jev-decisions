from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv", "dist", "build"}
SECRET_PATTERNS = [
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)(api[_ -]?key|token|password|secret)\s*[:=]\s*['\"](?!\.\.\.|YOUR_|CHANGEME|REDACTED)[^'\"]{12,}"),
]
PRIVATE_PATH_WORDS = {"sessions", "logs", "memories", "auth.json", ".env", "request_dump"}


def scan() -> list[str]:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.name in {"public_scan.py", "sync_from_hermes.py", ".env.example"}:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if any(word in relative.lower() for word in PRIVATE_PATH_WORDS):
            findings.append(f"private-looking path: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(f"secret-like content: {relative}:{number}")
                    break
    return findings


if __name__ == "__main__":
    findings = scan()
    if findings:
        print("Public scan failed:")
        print("\n".join(findings))
        sys.exit(1)
    print("Public scan passed: no private paths or secret-like content found")
