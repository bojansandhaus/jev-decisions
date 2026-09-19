"""Small append-only ledger for Jev outcomes, commitments, and decisions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .runtime import get_hermes_home
except ImportError:
    from runtime import get_hermes_home


def _path() -> Path:
    path = Path(get_hermes_home()) / "logs" / "jev-ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append(kind: str, payload: dict[str, Any]) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    basis = json.dumps({"kind": kind, "payload": payload, "timestamp": timestamp}, sort_keys=True, default=str)
    record_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    record = {"id": record_id, "kind": kind, "timestamp": timestamp, **payload}
    if kind == "review":
        record["review_id"] = record_id
    with _path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True, default=str) + "\n")
    return record_id


def read(limit: int = 200) -> list[dict[str, Any]]:
    path = _path()
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def metrics() -> dict[str, Any]:
    rows = read(5000)
    reviews = {row.get("review_id"): row for row in rows if row.get("kind") == "review" and row.get("review_id")}
    outcomes = [row for row in rows if row.get("kind") == "outcome"]
    by_review = {row.get("review_id"): row for row in outcomes if row.get("review_id")}
    correct = sum(1 for row in outcomes if row.get("correct") is True)
    return {
        "reviews": len(reviews),
        "outcomes": len(outcomes),
        "labeled_reviews": len(by_review),
        "unlabeled_reviews": max(0, len(reviews) - len(by_review)),
        "correct": correct,
        "incorrect": sum(1 for row in outcomes if row.get("correct") is False),
        "accuracy": round(correct / len(outcomes), 4) if outcomes else None,
        "kinds": sorted({str(row.get("kind")) for row in rows}),
    }
