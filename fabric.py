"""Cross system Jev case queue built on the append only ledger."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from .gateway import classify_case
    from .ledger import append, read
except ImportError:
    from gateway import classify_case
    from ledger import append, read


def open_case(domain: str, state: dict[str, Any], owner: str = "user") -> str:
    classification = classify_case(domain, state)
    case_id = append("case", {
        "status": "open",
        "domain": domain,
        "owner": owner,
        "state": state,
        "classification": classification,
        "opened_at": datetime.now(timezone.utc).isoformat(),
    })
    return case_id


def close_case(case_id: str, status: str, outcome: dict[str, Any] | None = None) -> str:
    return append("case_update", {
        "case_id": case_id,
        "status": status,
        "outcome": outcome or {},
        "closed_at": datetime.now(timezone.utc).isoformat(),
    })


def queue(status: str | None = None, domain: str | None = None) -> list[dict[str, Any]]:
    entries = read(500)
    cases = {x.get("id"): x for x in entries if x.get("kind") == "case"}
    for update in entries:
        if update.get("kind") != "case_update":
            continue
        case = cases.get(update.get("case_id"))
        if case:
            case["status"] = update.get("status", case.get("status"))
            case["last_update"] = update
    result = list(cases.values())
    for item in result:
        item.setdefault("case_id", item.get("id"))
    if status:
        result = [x for x in result if x.get("status") == status]
    if domain:
        result = [x for x in result if x.get("domain") == domain]
    return result
