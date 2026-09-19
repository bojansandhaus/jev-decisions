from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gateway  # noqa: E402
from tools import public_scan  # noqa: E402


def test_decide_keeps_destructive_actions_with_human() -> None:
    result = gateway.decide({"action": "delete_backup", "external": True})
    assert result["decision"] == "human"
    assert result["authority"] == "deterministic_policy"


def test_reversible_external_action_is_suggested() -> None:
    result = gateway.decide({"action": "restart_service", "external": True, "reversible": True})
    assert result["decision"] == "suggest"


def test_verification_requires_read_back_and_evidence() -> None:
    assert gateway.verify({"changed": True})["next"] == "read_back"
    assert gateway.verify({"changed": True, "read_back": True})["next"] == "inspect_evidence"
    assert gateway.verify({"changed": True, "read_back": True, "evidence": True})["verified"] is True


def test_domain_classification_is_conservative() -> None:
    assert gateway.classify_case("research", {})["decision"] == "hold"
    assert gateway.classify_case("health", {})["decision"] == "human"
    assert gateway.classify_case("communication", {"creates_commitment": True})["next"] == "record_commitment"


def test_public_scan_passes() -> None:
    assert public_scan.scan() == []
