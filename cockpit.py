"""Read only Jev cockpit summaries and bounded commitment detection."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from .fabric import queue
    from .ledger import append, metrics
except ImportError:
    from fabric import queue
    from ledger import append, metrics

_COMMITMENT = re.compile(r"(?im)^\s*((?:I|we)\s+(?:will|shall|am going to)\b[^.!?]{3,240}[.!?]?)")


def commitment_candidates(text: str, limit: int = 20) -> list[dict[str, Any]]:
    """Find candidate commitments without declaring them confirmed commitments."""
    return [{"text": match.group(1).strip(), "status": "candidate"}
            for match in list(_COMMITMENT.finditer(text))[:limit]]


def promote_commitment(text: str, owner: str = "beau", deadline: str | None = None, next_action: str | None = None) -> str:
    """Promote a reviewed candidate into a durable commitment record."""
    if not text.strip():
        raise ValueError("commitment text must not be empty")
    return append("commitment", {
        "text": text.strip(),
        "owner": owner,
        "deadline": deadline,
        "next_action": next_action or text.strip(),
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def stale_cases(days: int = 7) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    result = []
    for case in queue(status="open"):
        try:
            opened = datetime.fromisoformat(str(case.get("opened_at")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if opened < cutoff:
            result.append(case)
    return result


def digest() -> dict[str, Any]:
    report = snapshot()
    report["stale_cases"] = len(stale_cases())
    report["commitment_candidates"] = 0
    report["next_action"] = "review open cases and verify awaiting_verification results"
    return report

    cases = queue()
    open_cases = [case for case in cases if case.get("status") == "open"]
    domains = Counter(case.get("domain", "unknown") for case in open_cases)
    return {
        "open_cases": len(open_cases),
        "total_cases": len(cases),
        "by_domain": dict(sorted(domains.items())),
        "ledger": metrics(),
    }
