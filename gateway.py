"""Local deterministic policy and verification gateway for Jev integrations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from .ledger import append as append_ledger, metrics as ledger_metrics
except ImportError:
    from ledger import append as append_ledger, metrics as ledger_metrics


def decide(state: dict[str, Any]) -> dict[str, Any]:
    reversible = state.get("reversible", True)
    external = state.get("external", False)
    destructive = state.get("destructive", False) or str(state.get("action", "")).lower().startswith(("delete", "destroy", "wipe"))
    credential = state.get("credential", False)
    if destructive or credential or (external and not reversible):
        decision = "human"
    elif external:
        decision = "suggest"
    else:
        decision = "observe"
    return {
        "decision": decision,
        "authority": "deterministic_policy",
        "reason": {
            "destructive": destructive,
            "credential": credential,
            "external": external,
            "reversible": reversible,
        },
    }


def verify(state: dict[str, Any]) -> dict[str, Any]:
    changed = bool(state.get("changed"))
    read_back = bool(state.get("read_back"))
    evidence = bool(state.get("evidence"))
    if changed and not read_back:
        next_step = "read_back"
    elif changed and not evidence:
        next_step = "inspect_evidence"
    else:
        next_step = "done"
    return {
        "verified": bool((not changed) or (read_back and evidence)),
        "next": next_step,
        "authority": "deterministic_verification",
    }


def classify_case(domain: str, state: dict[str, Any]) -> dict[str, Any]:
    """Apply conservative domain rules before any model based review."""
    domain = str(domain).strip().lower()
    if domain == "home_assistant":
        service = str(state.get("service", ""))
        irreversible = not bool(state.get("reversible", True))
        sensitive = any(token in service for token in ("unlock", "disarm", "open_cover", "delete"))
        return {"domain": domain, "decision": "human" if irreversible or sensitive else "suggest", "next": "confirm" if irreversible or sensitive else "review"}
    if domain == "research":
        sources = state.get("sources")
        if not isinstance(sources, list) or not sources:
            return {"domain": domain, "decision": "hold", "next": "add_evidence"}
        return {"domain": domain, "decision": "review", "next": "assess_claim"}
    if domain == "communication":
        if state.get("creates_commitment"):
            return {"domain": domain, "decision": "review", "next": "record_commitment"}
        return {"domain": domain, "decision": "suggest", "next": "communication_review"}
    if domain in {"infrastructure", "docker", "nas"}:
        return {"domain": domain, "decision": decide(state)["decision"], "next": "verify_after_action"}
    if domain in {"paperless", "documents"}:
        return {"domain": domain, "decision": "review", "next": "document_quality"}
    if domain in {"purchase", "subscription"}:
        return {"domain": domain, "decision": "review", "next": "purchase_review"}
    if domain in {"health", "medical"}:
        return {"domain": domain, "decision": "human", "next": "professional_review"}
    return {"domain": domain, "decision": "review", "next": "jev_workflow"}


def record_outcome(review_id: str, correct: bool, details: dict[str, Any] | None = None) -> str:
    return append_ledger("outcome", {"review_id": review_id, "correct": bool(correct), "details": details or {}})


def record_commitment(text: str, owner: str | None = None, deadline: str | None = None) -> str:
    return append_ledger("commitment", {"text": text[:4000], "owner": owner, "deadline": deadline, "status": "open"})


def record_decision(text: str, status: str = "open", revisit: str | None = None) -> str:
    return append_ledger("decision", {"text": text[:4000], "status": status, "revisit": revisit})


def snapshot() -> dict[str, Any]:
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "ledger": ledger_metrics()}
