from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

from approval_policy import apply_policy
from approval_review import QUESTIONS, review_command
from jev_client import JevSchemaError, validate_answers


def answers(**overrides):
    value = {
        "verdict": {"choice": "APPROVE", "confidence": 0.9},
        "policy_allows": {"noul": 0.0},
        "blast_radius": {"score": 0.2},
        "self_advocating": {"noul": 0.0},
        "reads_secrets": {"noul": 0.0},
        "sends_outbound": {"noul": 0.0},
    }
    value.update(overrides)
    return value


def test_policy_downgrades_secret_exfiltration():
    decision = apply_policy(answers(reads_secrets={"noul": 0.9}, sends_outbound={"noul": 0.9}), has_policy=True)
    assert decision.verdict == "DENY"


def test_policy_rejects_self_advocacy_before_policy_upgrade():
    decision = apply_policy(answers(policy_allows={"noul": 0.99}, self_advocating={"noul": 0.9}), has_policy=True)
    assert decision.verdict == "ESCALATE"


def test_policy_upgrade_still_requires_confidence_and_blast_checks():
    low_confidence = apply_policy(
        answers(policy_allows={"noul": 0.99}, verdict={"choice": "DENY", "confidence": 0.54}),
        has_policy=True,
    )
    high_blast = apply_policy(
        answers(policy_allows={"noul": 0.99}, blast_radius={"score": 1.6}),
        has_policy=True,
    )
    assert low_confidence.verdict == "ESCALATE"
    assert high_blast.verdict == "ESCALATE"


@pytest.mark.parametrize("confidence", [True, False, float("nan"), float("inf"), -float("inf"), "0.9"])
def test_policy_rejects_malformed_confidence(confidence):
    with pytest.raises(ValueError, match="confidence"):
        apply_policy(answers(verdict={"choice": "APPROVE", "confidence": confidence}), has_policy=False)


def test_validation_rejects_missing_answer():
    with pytest.raises(JevSchemaError):
        validate_answers({}, QUESTIONS)


def test_review_is_bounded_and_advisory():
    def transport(payload, **_):
        return {"model": "fixture", "answers": answers(), "usage": {"total_tokens": 1}}

    result = review_command("printf hello", api_key="fixture", transport=transport)
    assert result["success"] is True
    assert result["shadow"] is True
    assert result["verdict"] == "APPROVE"
    assert "command" not in result


def test_truncated_approval_escalates():
    def transport(payload, **_):
        return {"answers": answers()}

    result = review_command("x" * 5000, api_key="fixture", transport=transport)
    assert result["truncated"] is True
    assert result["verdict"] == "ESCALATE"
