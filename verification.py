"""Deterministic, source specific observation verification."""
from __future__ import annotations

from typing import Any


def _text(result: Any) -> str:
    return str(result).strip().lower()


def verify_observation(source: str, context: dict[str, Any], result: Any) -> dict[str, Any]:
    source = str(source).lower()
    text = _text(result)
    if text.startswith("collector_error:") or "error" in text or "timeout" in text:
        return {"verified": False, "status": "unavailable", "next": "retry_or_inspect", "authority": "deterministic_verification"}
    expected = context.get("expected")
    if expected is None:
        expected = context.get("expected_state", context.get("expected_status"))
    if expected is None:
        return {"verified": False, "status": "observed", "next": "compare_expected", "authority": "deterministic_verification"}

    actual = result.get("state") if isinstance(result, dict) else result
    matches = _text(actual) == _text(expected)
    return {
        "verified": matches,
        "status": "matched" if matches else "mismatch",
        "next": "done" if matches else "read_back_expected",
        "authority": "deterministic_verification",
    }
