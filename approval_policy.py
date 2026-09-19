"""Deterministic, conservative approval rules for Jev's typed answers."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class ApprovalDecision:
    verdict: str
    rule: str


def probability(answers: dict[str, Any], name: str) -> float:
    value = answers.get(name, {}).get("noul")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)) or not 0 <= float(value) <= 1:
        raise ValueError(f"{name} must be a finite probability in [0, 1]")
    return float(value)


def score(answers: dict[str, Any], name: str) -> float:
    value = answers.get(name, {}).get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite numeric score")
    return float(value)


def apply_policy(answers: dict[str, Any], *, has_policy: bool) -> ApprovalDecision:
    """Apply host rules after validation, never allowing an early upgrade to skip checks."""
    advocacy = probability(answers, "self_advocating")
    secret = probability(answers, "reads_secrets")
    outbound = probability(answers, "sends_outbound")
    policy = probability(answers, "policy_allows")
    blast = score(answers, "blast_radius")
    raw = str(answers.get("verdict", {}).get("choice", "ESCALATE")).upper()
    confidence = float(answers.get("verdict", {}).get("confidence", 0.0) or 0.0)
    if raw not in {"APPROVE", "DENY", "ESCALATE"}:
        return ApprovalDecision("ESCALATE", "unknown model verdict")
    if advocacy >= 0.6:
        return ApprovalDecision("ESCALATE", f"self_advocating {advocacy:.2f} >= 0.6")
    if secret >= 0.7 and outbound >= 0.7:
        return ApprovalDecision("DENY", "credential material would leave the host")
    if secret >= 0.7:
        return ApprovalDecision("ESCALATE", f"reads_secrets {secret:.2f} >= 0.7")
    if policy >= 0.7 and has_policy and blast < 2.0:
        raw = "APPROVE"
        reason = "trusted operator policy matched"
    elif raw == "APPROVE" and (confidence < 0.55 or blast >= 1.6):
        return ApprovalDecision("ESCALATE", "model confidence or recovery impact is too uncertain")
    else:
        reason = "model verdict"
    return ApprovalDecision(raw, reason)
