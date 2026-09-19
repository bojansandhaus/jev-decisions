"""Route events from Hermes and connected systems into Jev cases."""
from __future__ import annotations

from typing import Any

try:
    from .fabric import close_case, open_case
except ImportError:
    from fabric import close_case, open_case

_ACTIVE_CASES: dict[str, list[str]] = {}
_ACTIVE_INVOCATIONS: dict[str, str] = {}


def _domain(source: str, event_type: str, payload: dict[str, Any]) -> str:
    text = f"{source} {event_type} {payload.get('tool_name', '')} {payload.get('service', '')}".lower()
    if source in {"telegram", "email", "discord", "matrix"} or event_type in {"draft", "message"}:
        return "communication"
    if "hindsight" in text or "memory" in text:
        return "hindsight"
    if "paperless" in text or event_type == "document":
        return "documents"
    if source in {"home_assistant", "ha"} or "home_assistant" in text:
        return "home_assistant"
    if event_type in {"tool_call", "service_change", "backup", "restore", "alert"}:
        return "infrastructure"
    if event_type in {"claim", "research", "citation"}:
        return "research"
    if event_type in {"purchase", "renewal"}:
        return "purchase"
    return "general"


def ingest_event(source: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    domain = _domain(source, event_type, payload)
    case_id = open_case(domain, {"source": source, "event_type": event_type, **payload})
    tool_name = payload.get("tool_name")
    if event_type == "tool_call" and tool_name:
        _ACTIVE_CASES.setdefault(str(tool_name), []).append(case_id)
        invocation_id = payload.get("invocation_id")
        if invocation_id:
            _ACTIVE_INVOCATIONS[str(invocation_id)] = case_id
    return {"case_id": case_id, "domain": domain, "source": source, "event_type": event_type}


def update_tool_result(
    tool_name: str,
    result: Any,
    verified: bool = False,
    invocation_id: str | None = None,
) -> str | None:
    case_id = (_ACTIVE_INVOCATIONS.get(str(invocation_id)) if invocation_id else None)
    if not case_id:
        pending = _ACTIVE_CASES.get(str(tool_name), [])
        case_id = pending[0] if pending else None
    if not case_id:
        return None
    status = "resolved" if verified else "awaiting_verification"
    close_case(case_id, status, {"tool_name": tool_name, "result": str(result)[:4000], "verified": verified})
    if verified:
        if invocation_id:
            _ACTIVE_INVOCATIONS.pop(str(invocation_id), None)
        pending = _ACTIVE_CASES.get(str(tool_name), [])
        if case_id in pending:
            pending.remove(case_id)
        if not pending:
            _ACTIVE_CASES.pop(str(tool_name), None)
    return case_id
