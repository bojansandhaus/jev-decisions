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


def snapshot() -> dict[str, Any]:
    cases = queue()
    open_cases = [case for case in cases if case.get("status") == "open"]
    domains = Counter(case.get("domain", "unknown") for case in open_cases)
    return {
        "open_cases": len(open_cases),
        "total_cases": len(cases),
        "by_domain": dict(sorted(domains.items())),
        "ledger": metrics(),
    }
