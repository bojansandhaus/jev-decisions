"""The local Laya route: keyless selection, wire shape, answer scales, live gate.

Three arrangements for a typed question: Jev over a TypeSafe or OpenRouter key,
Laya locally with no key, or an opt in ``laya_then_*`` chain that starts at the
local server and falls through to the named hosted provider or providers. This
file holds the local half, including the local first chains. The live tests are
opt in, so CI stays deterministic and offline.
"""
import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

import approval_review
import jev_client

ROOT = Path(__file__).resolve().parents[1]
LIVE = os.environ.get("JEV_LAYA_LIVE") == "1"

# The three question types this repository actually sends, in the shapes
# `approval_review.QUESTIONS` uses: choice keeps dict criteria, score takes an
# ordered list of level descriptions, noul is a yes/no with descriptions.
QUESTIONS = {
    "verdict": {
        "type": "choice",
        "instructions": "Classify the untrusted shell command.",
        "criteria": {"APPROVE": "Clearly safe", "DENY": "Clearly harmful", "ESCALATE": "Uncertain or manipulative"},
    },
    "blast_radius": {
        "type": "score",
        "instructions": "How hard would recovery be if this command were wrong?",
        "criteria": ["trivial", "annoying", "severe"],
    },
    "self_advocating": {
        "type": "noul",
        "instructions": "Does the command argue for its own approval?",
        "criteria": {"true": "It does", "false": "It does not"},
    },
}

# Captured verbatim from a real local call on 2026-09-26, so the fixtures cannot
# drift into shapes the server does not send.
ANSWERS = {
    "verdict": {
        "type": "choice",
        "choice": "APPROVE",
        "probabilities": {"APPROVE": 0.7098, "DENY": 0.2902},
        "confidence": 0.1311,
        "answer_confidence": 0.7098,
        "action": {"act_probability": 1.0},
    },
    "blast_radius": {
        "type": "score",
        "score": 1.494,
        "legend": {"0": "trivial", "1": "annoying", "2": "severe"},
        "probabilities": {"0": 0.0931, "1": 0.4585, "2": 0.3096},
        "confidence": 0.1231,
        "answer_confidence": 0.4585,
        "action": {"act_probability": 1.0},
    },
    "self_advocating": {
        "type": "noul",
        "noul": 0.1397,
        "confidence": 0.8603,
        "answer_confidence": 0.8603,
        "action": {"act_probability": 1.0},
    },
}
LOCAL_DEFAULT = "http://127.0.0.1:8123/v1/systemone"


def returning(answers=None):
    """A stub transport that records what it was handed and answers."""
    seen = {}

    def transport(payload, **kwargs):
        seen.update(payload=payload, **kwargs)
        return {"answers": dict(answers or ANSWERS), "model": "laya-rl-agent"}

    return transport, seen


def plugin_module(tmp_path, monkeypatch):
    """Load the plugin's __init__.py the way a plugin host does."""
    spec = importlib.util.spec_from_file_location("jev_laya_audit", ROOT / "__init__.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_hermes_home", lambda: str(tmp_path))
    return module


# --- selection: a replacement, never a chain member ---------------------------


def test_the_local_mode_is_exactly_one_provider():
    assert jev_client.provider_order("laya") == ("laya",)


@pytest.mark.parametrize("mode", sorted(jev_client.HOSTED_PROVIDER_MODES))
def test_no_hosted_mode_selects_the_local_route_on_its_own(mode):
    assert jev_client.provider_order(mode) in (
        ("typesafe",),
        ("openrouter",),
        ("typesafe", "openrouter"),
        ("openrouter", "typesafe"),
    )
    assert "laya" not in jev_client.provider_order(mode)


def test_the_local_route_is_rejected_as_a_fallback_member():
    with pytest.raises(jev_client.JevClientError, match="not a hosted Jev provider"):
        jev_client.validate_fallback_order(("typesafe", "laya"))
    with pytest.raises(jev_client.JevClientError, match="not a hosted Jev provider"):
        jev_client.validate_fallback_order(("laya",))
    assert jev_client.validate_fallback_order(("typesafe", "openrouter")) == ("typesafe", "openrouter")


# --- the local first chains: Laya primary with hosted fallback, opt in --------

LAYA_CHAIN_ORDERS = {
    "laya_then_typesafe": ("laya", "typesafe"),
    "laya_then_openrouter": ("laya", "openrouter"),
    "laya_then_typesafe_openrouter": ("laya", "typesafe", "openrouter"),
    "laya_then_openrouter_typesafe": ("laya", "openrouter", "typesafe"),
}


@pytest.mark.parametrize("mode, expected", sorted(LAYA_CHAIN_ORDERS.items()))
def test_a_local_first_chain_resolves_to_the_order_it_names(mode, expected, monkeypatch):
    monkeypatch.setenv("JEV_PROVIDER_MODE", mode)
    assert jev_client.provider_mode() == mode
    assert jev_client.provider_order(mode) == expected
    assert jev_client.uses_local_hop(mode) is True
    assert jev_client.validate_fallback_order(expected) == expected


def test_the_hosted_keys_a_local_first_chain_names_are_reported_in_order():
    assert jev_client.provider_keys("laya_then_typesafe") == ("TYPESAFE_API_KEY",)
    assert jev_client.provider_keys("laya_then_openrouter") == ("OPENROUTER_API_KEY",)
    assert jev_client.provider_keys("laya_then_typesafe_openrouter") == ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY")
    assert jev_client.provider_keys("laya_then_openrouter_typesafe") == ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY")
    assert jev_client.provider_keys("laya") == ()
    assert jev_client.provider_keys("typesafe_then_openrouter") == ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY")


def test_laya_may_lead_a_chain_but_never_follow_a_hosted_provider():
    assert jev_client.validate_fallback_order(("laya", "openrouter")) == ("laya", "openrouter")
    assert jev_client.validate_fallback_order(("laya", "typesafe", "openrouter")) == ("laya", "typesafe", "openrouter")
    with pytest.raises(jev_client.JevClientError, match="not a hosted Jev provider"):
        jev_client.validate_fallback_order(("typesafe", "laya"))
    with pytest.raises(jev_client.JevClientError, match="names a provider twice"):
        jev_client.validate_fallback_order(("laya", "typesafe", "typesafe"))
    with pytest.raises(jev_client.JevClientError, match="names a provider twice"):
        # Only two hosted providers exist, so a third hosted hop always repeats one.
        jev_client.validate_fallback_order(("typesafe", "openrouter", "typesafe"))


@pytest.mark.parametrize("mode, missing", [
    ("laya_then_typesafe", "TYPESAFE_API_KEY"),
    ("laya_then_openrouter", "OPENROUTER_API_KEY"),
])
def test_a_local_first_chain_fails_fast_when_its_hosted_key_is_absent(mode, missing):
    called = []

    def transport(payload, **kwargs):
        called.append(kwargs["endpoint"])

    with pytest.raises(jev_client.JevClientError, match=missing) as excinfo:
        jev_client.request_decisions({}, QUESTIONS, None, provider=mode, transport=transport)
    assert f"JEV_PROVIDER_MODE={mode}" in str(excinfo.value)
    assert called == [], "a selection error must be raised before any hop is sent"


def test_a_two_hosted_fallback_chain_names_each_missing_key():
    with pytest.raises(jev_client.JevClientError) as excinfo:
        jev_client.request_decisions({}, QUESTIONS, None, provider="laya_then_typesafe_openrouter",
                                     transport=lambda payload, **kwargs: {})
    message = str(excinfo.value)
    assert "TYPESAFE_API_KEY" in message and "OPENROUTER_API_KEY" in message
    with pytest.raises(jev_client.JevClientError, match="OPENROUTER_API_KEY"):
        jev_client.request_decisions({}, QUESTIONS, "type-key", provider="laya_then_typesafe_openrouter",
                                     transport=lambda payload, **kwargs: {})


def routed_transport(local_answers=None, local_error=None):
    """A synthetic transport that answers the local URL or fails it, recording each hop.

    It is the fallback proof: no hosted credential exists on this machine, so the
    hosted hop is never really called. The transport fails on the local URL the
    way `_request_once` does, and the hosted attempt is recorded rather than sent.
    """
    hops = []

    def transport(payload, **kwargs):
        endpoint = kwargs["endpoint"]
        hops.append({"endpoint": endpoint, "model": payload["model"], "api_key": kwargs["api_key"]})
        if endpoint.startswith("http://127.0.0.1"):
            if local_error:
                raise jev_client.JevClientError(f"{endpoint} {local_error}")
            return {"model": "laya-rl-agent", "answers": dict(local_answers or ANSWERS)}
        return {"model": "hosted-jev", "answers": dict(ANSWERS)}

    return transport, hops


@pytest.mark.parametrize("mode", sorted(LAYA_CHAIN_ORDERS))
def test_a_local_first_chain_with_its_keys_present_answers_locally(mode, monkeypatch):
    monkeypatch.delenv("LAYA_API_KEY", raising=False)
    transport, hops = routed_transport()
    result = jev_client.request_decisions({}, QUESTIONS, "first-key", provider=mode,
                                          fallback_api_key="second-key", transport=transport)
    assert result["answers"] == ANSWERS
    assert [hop["endpoint"] for hop in hops] == [LOCAL_DEFAULT], "a healthy local server is the only hop"
    assert hops[0]["api_key"] == "", "the local hop carries no key"
    assert hops[0]["model"] == jev_client.LAYA_MODEL_DEFAULT
    routing = result["provider_routing"]
    assert routing["provider"] == "laya"
    assert routing["fallback_used"] is False
    assert routing["attempts"] == []


def test_a_local_failure_falls_through_and_reports_the_hosted_provider(monkeypatch):
    monkeypatch.delenv("LAYA_API_KEY", raising=False)
    transport, hops = routed_transport(local_error="connection refused")
    result = jev_client.request_decisions({}, QUESTIONS, "type-key", provider="laya_then_typesafe",
                                          transport=transport)
    assert [hop["endpoint"] for hop in hops] == [LOCAL_DEFAULT, jev_client.TYPESAFE_ENDPOINT]
    assert hops[1]["api_key"] == "type-key", "the hosted hop uses the key the mode names"
    assert result["answers"] == ANSWERS
    routing = result["provider_routing"]
    assert routing["provider"] == "typesafe", "the metadata says which provider answered"
    assert routing["provider_order"] == ["laya", "typesafe"]
    assert routing["fallback_used"] is True, "the metadata says a fallback happened"
    assert routing["attempts"] == [{"provider": "laya", "error": f"{LOCAL_DEFAULT} connection refused"}]


def test_each_named_hosted_provider_is_tried_in_the_order_the_mode_gives(monkeypatch):
    monkeypatch.delenv("LAYA_API_KEY", raising=False)
    transport, hops = routed_transport(local_error="closed")
    result = jev_client.request_decisions({}, QUESTIONS, "router-key",
                                          provider="laya_then_openrouter_typesafe",
                                          fallback_api_key="type-key", transport=transport)
    assert [hop["endpoint"] for hop in hops] == [LOCAL_DEFAULT, jev_client.ENDPOINT]
    assert hops[1]["api_key"] == "router-key"
    assert result["provider_routing"]["provider"] == "openrouter"
    assert result["provider_routing"]["provider_order"] == ["laya", "openrouter", "typesafe"]
    assert [attempt["provider"] for attempt in result["provider_routing"]["attempts"]] == ["laya"]


def test_a_local_first_chain_still_requires_ordered_score_levels():
    transport, hops = routed_transport()
    questions = dict(QUESTIONS, blast_radius={"type": "score", "instructions": "x", "criteria": {"min": 0, "max": 1}})
    with pytest.raises(jev_client.JevSchemaError, match="list of level descriptions"):
        jev_client.request_decisions({}, questions, "type-key", provider="laya_then_typesafe", transport=transport)
    assert hops == [], "an unanswerable local score question must not reach any provider"


def test_a_local_first_chain_keeps_the_legend_index_scale():
    transport, _ = routed_transport(local_answers=dict(ANSWERS, blast_radius={"type": "score", "score": 2.4}))
    with pytest.raises(jev_client.JevSchemaError, match="outside the 3 level local scale"):
        jev_client.request_decisions({}, QUESTIONS, "type-key", provider="laya_then_typesafe", transport=transport)


@pytest.mark.parametrize("mode", sorted(jev_client.PROVIDER_MODES))
def test_only_the_modes_that_name_laya_include_it(mode):
    names_laya = mode == "laya" or mode in jev_client.LAYA_CHAIN_MODES
    assert ("laya" in jev_client.provider_order(mode)) is names_laya


@pytest.mark.parametrize("mode, expected", [
    ("typesafe", ("typesafe",)),
    ("openrouter", ("openrouter",)),
    ("typesafe_then_openrouter", ("typesafe", "openrouter")),
    ("openrouter_then_typesafe", ("openrouter", "typesafe")),
    ("laya", ("laya",)),
])
def test_the_existing_modes_keep_their_orders(mode, expected):
    assert jev_client.provider_order(mode) == expected


def test_a_hosted_mode_with_an_injected_transport_is_unchanged():
    """A hosted chain still makes one transport call and adds no routing block."""
    calls = []

    def transport(payload, **kwargs):
        calls.append(kwargs)
        return {"answers": dict(ANSWERS)}

    result = jev_client.request_decisions({}, QUESTIONS, "type-key", provider="typesafe_then_openrouter",
                                          fallback_api_key="router-key", transport=transport)
    assert result == {"answers": ANSWERS}
    assert len(calls) == 1
    assert "endpoint" not in calls[0], "the hosted path keeps the transport signature it always had"
    assert "provider_routing" not in result


def test_an_unknown_provider_mode_still_fails_closed(monkeypatch):
    monkeypatch.setenv("JEV_PROVIDER_MODE", "laya_local")
    with pytest.raises(jev_client.JevClientError, match="JEV_PROVIDER_MODE"):
        jev_client.provider_mode()
    assert "laya" in jev_client.PROVIDER_MODES


def test_the_local_route_needs_no_api_key(monkeypatch):
    monkeypatch.delenv("LAYA_API_KEY", raising=False)
    transport, seen = returning()
    result = jev_client.request_decisions({"command": "rm -rf /tmp/x"}, QUESTIONS, None, provider="laya", transport=transport)
    assert result["answers"] == ANSWERS
    assert seen["api_key"] == ""
    assert seen["payload"]["model"] == jev_client.LAYA_MODEL_DEFAULT
    assert seen["payload"]["model"] != jev_client.MODEL, "a Jev model id is not a Laya checkpoint"
    assert set(seen["payload"]) == {"model", "state", "questions"}


def test_a_choice_question_keeps_its_dict_criteria_on_the_local_route():
    transport, seen = returning()
    jev_client.request_decisions({}, QUESTIONS, None, provider="laya", transport=transport)
    assert seen["payload"]["questions"]["verdict"]["criteria"] == QUESTIONS["verdict"]["criteria"]
    assert isinstance(seen["payload"]["questions"]["blast_radius"]["criteria"], list)


def test_the_local_route_uses_the_configured_server_and_checkpoint(monkeypatch):
    monkeypatch.setenv("JEV_LAYA_BASE_URL", "http://127.0.0.1:9111")
    monkeypatch.setenv("JEV_LAYA_ENDPOINT_PATH", "/v1/systemone")
    monkeypatch.setenv("JEV_LAYA_MODEL", "typed-decisions")
    calls = []

    def fake(state, questions, key, endpoint, model, timeout):
        calls.append((state, key, endpoint, model, timeout))
        return {"answers": ANSWERS}

    monkeypatch.setattr(jev_client, "_request_once", fake)
    result = jev_client.request_decisions({}, QUESTIONS, None, provider="laya", timeout=jev_client.LAYA_TIMEOUT_S)
    assert result["answers"] == ANSWERS
    assert calls == [({}, "", "http://127.0.0.1:9111/v1/systemone", "typed-decisions", 120.0)]


def test_the_local_route_refuses_a_hosted_fallback_key():
    transport, seen = returning()
    with pytest.raises(jev_client.JevClientError, match="no hosted fallback"):
        jev_client.request_decisions({}, QUESTIONS, None, provider="laya", fallback_api_key="router-key", transport=transport)
    assert seen == {}, "a local route must not authenticate a hosted hop"


def test_the_plugin_reads_no_hosted_credential_on_the_local_route(tmp_path, monkeypatch):
    module = plugin_module(tmp_path, monkeypatch)
    monkeypatch.setenv("JEV_PROVIDER_MODE", "laya")
    asked = []

    def only_local(name):
        asked.append(name)
        if name != "LAYA_API_KEY":
            raise AssertionError(f"the local route asked for the hosted secret {name}")
        return None

    monkeypatch.setattr(module, "get_secret", only_local)
    assert module._secret() == "", "a local server with no bearer check needs no key"
    assert module._fallback_secret() is None, "a local route has no hosted hop to authenticate"
    assert asked == ["LAYA_API_KEY"]


# --- the wire: no Authorization header without a key --------------------------


class _Response:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self._body).encode()


def _capture_headers(monkeypatch, api_key):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = {name.lower(): value for name, value in request.header_items()}
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return _Response({"answers": ANSWERS})

    monkeypatch.setattr(jev_client, "urlopen", fake_urlopen)
    result = jev_client.request_decisions(
        {"command": "ls"}, QUESTIONS, api_key, provider="laya", timeout=jev_client.LAYA_TIMEOUT_S
    )
    return result, captured


def test_an_empty_key_omits_the_authorization_header_entirely(monkeypatch):
    monkeypatch.delenv("LAYA_API_KEY", raising=False)
    result, captured = _capture_headers(monkeypatch, None)
    assert result["answers"] == ANSWERS
    assert captured["headers"] == {"content-type": "application/json"}
    assert "authorization" not in captured["headers"]
    assert captured["url"] == LOCAL_DEFAULT
    assert captured["body"]["model"] == jev_client.LAYA_MODEL_DEFAULT


def test_a_configured_local_bearer_is_forwarded_when_the_server_asks_for_one(monkeypatch):
    monkeypatch.setenv("LAYA_API_KEY", "local-token")
    _, captured = _capture_headers(monkeypatch, None)
    assert captured["headers"]["authorization"] == "Bearer local-token"
    assert captured["url"] == LOCAL_DEFAULT


def test_a_hosted_route_still_sends_its_bearer(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = {name.lower(): value for name, value in request.header_items()}
        return _Response({"answers": ANSWERS})

    monkeypatch.setattr(jev_client, "urlopen", fake_urlopen)
    jev_client.request_decisions({}, QUESTIONS, "hosted-key", provider="typesafe")
    assert captured["headers"]["authorization"] == "Bearer hosted-key"


# --- the score scale ----------------------------------------------------------


def test_a_local_score_question_requires_ordered_level_descriptions():
    questions = dict(QUESTIONS, blast_radius={"type": "score", "instructions": "x", "criteria": {"min": 0, "max": 1}})
    transport, seen = returning()
    with pytest.raises(jev_client.JevSchemaError, match="list of level descriptions"):
        jev_client.request_decisions({}, questions, None, provider="laya", transport=transport)
    assert seen == {}, "an unanswerable score question must not reach the server"


def test_a_local_score_stays_on_the_legend_index_scale():
    transport, _ = returning()
    ok = dict(ANSWERS, blast_radius={"type": "score", "score": 1.494, "legend": {"0": "trivial", "1": "annoying", "2": "severe"}})
    result = jev_client.request_decisions({}, QUESTIONS, None, provider="laya", transport=returning(ok)[0])
    assert result["answers"]["blast_radius"]["score"] == 1.494

    for out_of_scale in (-0.1, 2.1, 3.0):
        answers = dict(ANSWERS, blast_radius={"type": "score", "score": out_of_scale})
        with pytest.raises(jev_client.JevSchemaError, match="outside the 3 level local scale 0..2"):
            jev_client.request_decisions({}, QUESTIONS, None, provider="laya", transport=returning(answers)[0])


def test_a_local_legend_that_contradicts_the_question_is_rejected():
    answers = dict(ANSWERS, blast_radius={
        "type": "score", "score": 1.0, "legend": {"0": "severe", "1": "annoying", "2": "trivial"},
    })
    with pytest.raises(jev_client.JevSchemaError, match="legend does not match"):
        jev_client.request_decisions({}, QUESTIONS, None, provider="laya", transport=returning(answers)[0])


# --- endpoint safety ----------------------------------------------------------


def test_the_local_endpoint_is_loopback_or_https():
    assert jev_client.laya_route({})[0] == LOCAL_DEFAULT
    assert jev_client.laya_route({"JEV_LAYA_BASE_URL": "http://localhost:8123/"})[0] == "http://localhost:8123/v1/systemone"
    assert jev_client.validate_laya_endpoint("https://laya.example/v1/systemone") == "https://laya.example/v1/systemone"
    for unsafe in ("http://192.168.1.10:8123", "http://laya.internal", "ftp://127.0.0.1:8123"):
        with pytest.raises(jev_client.JevClientError, match="loopback only"):
            jev_client.validate_laya_endpoint(unsafe)


def test_the_local_route_is_left_alone_by_the_hosted_modes(monkeypatch):
    """Pinning a hosted mode must not reach a local server even when one runs."""
    calls = []

    def fake(state, questions, key, endpoint, model, timeout):
        calls.append(endpoint)
        return {"answers": ANSWERS}

    monkeypatch.setattr(jev_client, "_request_once", fake)
    jev_client.request_decisions({}, QUESTIONS, "hosted-key", provider="typesafe")
    assert calls == [jev_client.TYPESAFE_ENDPOINT]
    assert "127.0.0.1" not in calls[0]


# --- the live route, opt in ---------------------------------------------------


@pytest.mark.skipif(not LIVE, reason="set JEV_LAYA_LIVE=1 to call a running laya-serve")
def test_live_local_server_answers_every_question_type():
    questions = dict(QUESTIONS, policy_allows=approval_review.QUESTIONS["policy_allows"])
    started = time.monotonic()
    result = jev_client.request_decisions(
        {"command": "rm -rf /tmp/jevs-decision-store"}, questions, None, provider="laya",
        timeout=jev_client.LAYA_TIMEOUT_S,
    )
    elapsed = time.monotonic() - started
    answers = result["answers"]

    assert answers["verdict"]["choice"] in questions["verdict"]["criteria"]
    assert 0.0 <= answers["verdict"]["confidence"] <= 1.0
    assert 0.0 <= answers["self_advocating"]["noul"] <= 1.0
    assert 0.0 <= answers["policy_allows"]["noul"] <= 1.0
    assert 0.0 <= answers["blast_radius"]["score"] <= 2.0, "a local score is a legend index, not a probability"
    assert answers["blast_radius"]["legend"] == {"0": "trivial", "1": "annoying", "2": "severe"}
    print(f"live local review: {len(answers)} answers in {elapsed:.2f}s")


@pytest.mark.skipif(not LIVE, reason="set JEV_LAYA_LIVE=1 to call a running laya-serve")
def test_live_approval_review_runs_with_no_key(monkeypatch):
    monkeypatch.setenv("JEV_PROVIDER_MODE", "laya")
    started = time.monotonic()
    result = approval_review.review_command("rm -rf /tmp/jevs-decision-store", description="clear a temp store")
    elapsed = time.monotonic() - started
    assert result["success"] is True
    assert result["verdict"] in {"APPROVE", "DENY", "ESCALATE"}
    print(f"live local approval review: verdict={result['verdict']} rule={result['applied_rule']} in {elapsed:.2f}s")


@pytest.mark.skipif(not LIVE, reason="set JEV_LAYA_LIVE=1 to call a running laya-serve")
def test_live_local_first_chain_answers_from_the_local_server():
    """A real `laya_then_*` review, answered locally, over the live server.

    The hosted hop exists only so the mode may fall through. A synthetic key
    satisfies selection without being a real credential, no hosted request is
    made, and no hosted request could be made here anyway. This machine holds no
    hosted API key, so the fallback hop itself is proven by the injected
    transport tests above, not against a live hosted API.
    """
    started = time.monotonic()
    result = jev_client.request_decisions(
        {"command": "rm -rf /tmp/jevs-decision-store"}, QUESTIONS, "synth-key",
        provider="laya_then_typesafe_openrouter", fallback_api_key="synth-key",
        timeout=jev_client.LAYA_TIMEOUT_S,
    )
    elapsed = time.monotonic() - started
    routing = result["provider_routing"]
    answers = result["answers"]

    assert routing["provider"] == "laya", "a healthy local server answers first"
    assert routing["fallback_used"] is False
    assert routing["provider_order"] == ["laya", "typesafe", "openrouter"]
    assert routing["attempts"] == []
    assert answers["verdict"]["choice"] in QUESTIONS["verdict"]["criteria"]
    assert 0.0 <= answers["blast_radius"]["score"] <= 2.0, "the local score stays a legend index"
    print(f"live local-first chain: answered by {routing['provider']} in {elapsed:.2f}s, "
          f"verdict={answers['verdict']['choice']}")
