import pytest

import jev_client


QUESTIONS = {
    "ok": {
        "type": "noul",
        "instructions": "Is this a fixture?",
        "criteria": {"true": "It is", "false": "It is not"},
    }
}
ANSWER = {"answers": {"ok": {"noul": 1.0}}}


def test_provider_modes_are_explicit(monkeypatch):
    for mode in ("typesafe", "openrouter", "typesafe_then_openrouter", "openrouter_then_typesafe"):
        monkeypatch.setenv("JEV_PROVIDER_MODE", mode)
        assert jev_client.provider_mode() == mode


def test_unknown_provider_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("JEV_PROVIDER_MODE", "typeface")
    with pytest.raises(jev_client.JevClientError, match="JEV_PROVIDER_MODE"):
        jev_client.provider_mode()


def test_typesafe_primary_uses_direct_endpoint(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(args)
        return ANSWER

    monkeypatch.setattr(jev_client, "_request_once", fake)
    result = jev_client.request_decisions({}, QUESTIONS, "type-key", provider="typesafe")
    assert result == ANSWER
    assert calls == [({}, QUESTIONS, "type-key", jev_client.TYPESAFE_ENDPOINT, jev_client.TYPESAFE_MODEL, 30.0)]


def test_typesafe_primary_falls_back_to_openrouter(monkeypatch):
    calls = []

    def fake(state, questions, key, endpoint, model, timeout):
        calls.append((key, endpoint, model))
        if endpoint == jev_client.TYPESAFE_ENDPOINT:
            raise jev_client.JevClientError("TypeSafe unavailable")
        return ANSWER

    monkeypatch.setattr(jev_client, "_request_once", fake)
    result = jev_client.request_decisions(
        {}, QUESTIONS, "type-key", provider="typesafe_then_openrouter", fallback_api_key="router-key"
    )
    assert result == ANSWER
    assert calls == [
        ("type-key", jev_client.TYPESAFE_ENDPOINT, jev_client.TYPESAFE_MODEL),
        ("router-key", jev_client.ENDPOINT, jev_client.MODEL),
    ]


def test_openrouter_primary_falls_back_to_typesafe(monkeypatch):
    calls = []

    def fake(state, questions, key, endpoint, model, timeout):
        calls.append((key, endpoint, model))
        if endpoint == jev_client.ENDPOINT:
            raise jev_client.JevClientError("OpenRouter unavailable")
        return ANSWER

    monkeypatch.setattr(jev_client, "_request_once", fake)
    result = jev_client.request_decisions(
        {}, QUESTIONS, "router-key", provider="openrouter_then_typesafe", fallback_api_key="type-key"
    )
    assert result == ANSWER
    assert calls == [
        ("router-key", jev_client.ENDPOINT, jev_client.MODEL),
        ("type-key", jev_client.TYPESAFE_ENDPOINT, jev_client.TYPESAFE_MODEL),
    ]
