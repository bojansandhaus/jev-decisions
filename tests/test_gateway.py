from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gateway  # noqa: E402
import closed_loop  # noqa: E402
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


def test_verification_does_not_treat_missing_change_as_success() -> None:
    result = gateway.verify({})
    assert result["verified"] is False
    assert result["next"] == "establish_change"


def test_verification_requires_boolean_proof_fields() -> None:
    result = gateway.verify({"changed": True, "read_back": "yes", "evidence": ["claimed"]})
    assert result["verified"] is False
    assert result["next"] == "read_back"


def test_domain_classification_is_conservative() -> None:
    assert gateway.classify_case("research", {})["decision"] == "hold"
    assert gateway.classify_case("health", {})["decision"] == "human"
    assert gateway.classify_case("communication", {"creates_commitment": True})["next"] == "record_commitment"


def test_public_scan_passes() -> None:
    assert public_scan.scan() == []


def test_closed_loop_preserves_unknown_outcome(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JEV_HOME", str(tmp_path))
    decision = closed_loop.record_decision("Question", "observe")
    closed_loop.record_outcome(decision["decision_id"], "unknown", None)
    records = closed_loop.list_records()
    assert records[-1]["success"] is None


def test_networked_hooks_are_opt_in(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("jev_plugin_module", ROOT / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(plugin)

    class Context:
        def __init__(self):
            self.hooks = []

        def register_tool(self, *args, **kwargs):
            pass

        def register_hook(self, name, callback):
            self.hooks.append(name)

    context = Context()
    monkeypatch.delenv("JEV_ENABLE_HOOKS", raising=False)
    plugin.register(context)
    assert context.hooks == ["post_llm_call", "post_tool_call", "pre_tool_call"]

    context = Context()
    monkeypatch.setenv("JEV_ENABLE_HOOKS", "true")
    plugin.register(context)
    assert context.hooks == ["post_llm_call", "post_tool_call", "pre_tool_call"]


def test_disabled_hook_does_not_call_provider_or_persist(monkeypatch, tmp_path) -> None:
    spec = importlib.util.spec_from_file_location("jev_plugin_disabled", ROOT / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(plugin)
    monkeypatch.delenv("JEV_ENABLE_HOOKS", raising=False)
    monkeypatch.setenv("JEV_HOME", str(tmp_path))
    plugin._on_post_tool_call("example", {"changed": True}, "private result")
    assert list(tmp_path.rglob("*")) == []
