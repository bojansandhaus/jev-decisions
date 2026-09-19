"""Closed loop decision journal for Jev.

This module records decisions, evidence, observations, and outcomes without
changing execution authority. It produces deterministic calibration signals.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .runtime import get_hermes_home
except ImportError:
    from runtime import get_hermes_home


def _path() -> Path:
    path = Path(get_hermes_home()) / "logs" / "jev-closed-loop.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append(kind: str, payload: dict[str, Any], record_id: str | None = None) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    import hashlib
    basis = json.dumps({"kind": kind, "payload": payload, "timestamp": timestamp}, sort_keys=True, default=str)
    record_id = record_id or hashlib.sha256(basis.encode()).hexdigest()[:16]
    record = {"id": record_id, "kind": kind, "timestamp": timestamp, **payload}
    if kind == "decision":
        record["decision_id"] = record_id
    with _path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return record_id


def _read() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def record_decision(
    question: str,
    chosen: str,
    options: list[str] | None = None,
    evidence: list[Any] | None = None,
    assumptions: list[str] | None = None,
    owner: str = "user",
    deadline: str | None = None,
    decision_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "question": question[:4000],
        "chosen": chosen[:1000],
        "options": (options or [])[:20],
        "evidence": (evidence or [])[:20],
        "assumptions": (assumptions or [])[:20],
        "owner": owner,
        "deadline": deadline,
    }
    decision_id = _append("decision", payload, decision_id)
    return {"decision_id": decision_id, "kind": "decision"}


def record_observation(decision_id: str, observation: str, source: str, supports: bool | None = None) -> dict[str, Any]:
    observation_id = _append("observation", {
        "decision_id": decision_id,
        "observation": observation[:4000],
        "source": source[:500],
        "supports": supports,
    })
    return {"observation_id": observation_id, "decision_id": decision_id, "kind": "observation"}


def record_outcome(decision_id: str, status: str, success: bool | None, evidence: Any = None, notes: str = "") -> dict[str, Any]:
    outcome_id = _append("outcome", {
        "decision_id": decision_id,
        "status": status[:500],
        "success": success if isinstance(success, bool) else None,
        "evidence": evidence,
        "notes": notes[:4000],
    })
    return {"outcome_id": outcome_id, "decision_id": decision_id, "kind": "outcome"}


def assess(decision_id: str) -> dict[str, Any]:
    rows = [row for row in _read() if row.get("decision_id") == decision_id]
    decision = next((row for row in rows if row.get("kind") == "decision"), None)
    outcomes = [row for row in rows if row.get("kind") == "outcome" and isinstance(row.get("success"), bool)]
    successes = sum(1 for row in outcomes if row.get("success") is True)
    accuracy = round(successes / len(outcomes), 4) if outcomes else None
    if len(outcomes) >= 5 and accuracy is not None and (accuracy <= 0.6 or accuracy >= 0.9):
        recommendation = "change_behavior"
        reason = "repeated outcomes provide enough evidence to review the current behavior"
    elif outcomes:
        recommendation = "continue_observing"
        reason = "outcome evidence exists but is not yet decisive"
    else:
        recommendation = "collect_outcome"
        reason = "the decision has no recorded outcome"
    return {
        "decision_id": decision_id,
        "found": decision is not None,
        "question": decision.get("question") if decision else None,
        "chosen": decision.get("chosen") if decision else None,
        "observations": sum(1 for row in rows if row.get("kind") == "observation"),
        "outcomes": len(outcomes),
        "successes": successes,
        "accuracy": accuracy,
        "recommendation": recommendation,
        "reason": reason,
    }


def list_records(limit: int = 100) -> list[dict[str, Any]]:
    return _read()[-max(1, min(limit, 500)):]
