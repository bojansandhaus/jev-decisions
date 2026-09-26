"""Shared bounded client for Jev over a TypeSafe or OpenRouter key, or Laya locally.

Two mutually exclusive ways to answer a typed question: a hosted Jev provider
behind an API key, or a local `laya-serve` process that needs no key at all.
The local route replaces the hosted one rather than joining the fallback chain.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
TYPESAFE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODEL = "jev-1.13.0"
TYPESAFE_PROVIDER = "typesafe"
OPENROUTER_PROVIDER = "openrouter"
LAYA_PROVIDER = "laya"
HOSTED_PROVIDER_MODES = frozenset({
    TYPESAFE_PROVIDER, OPENROUTER_PROVIDER,
    "typesafe_then_openrouter", "openrouter_then_typesafe",
})
PROVIDER_MODES = HOSTED_PROVIDER_MODES | {LAYA_PROVIDER}
# A provider bound to the local machine carries no credential requirement, so an
# empty key means "send no Authorization header", not "disabled".
KEYLESS_PROVIDERS = frozenset({LAYA_PROVIDER})
FALLBACK_ORDER: dict[str, tuple[str, ...]] = {
    "typesafe_then_openrouter": (TYPESAFE_PROVIDER, OPENROUTER_PROVIDER),
    "openrouter_then_typesafe": (OPENROUTER_PROVIDER, TYPESAFE_PROVIDER),
}
LAYA_BASE_URL_DEFAULT = "http://127.0.0.1:8123"
LAYA_ENDPOINT_PATH_DEFAULT = "/v1/systemone"
LAYA_MODEL_DEFAULT = "english"
# CPU inference on the base checkpoint measured about 1.6 seconds per question
# row and roughly 2 seconds for a whole six question review on 2026-09-26, so the
# local route gets a longer budget than the hosted default of 30 seconds.
LAYA_TIMEOUT_S = 120.0
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


class JevClientError(RuntimeError):
    """Base error for unavailable or invalid Jev responses."""


class JevSchemaError(JevClientError):
    """The provider returned a response outside the typed contract."""


def provider_mode(value: str | None = None) -> str:
    """Return the selected route, defaulting to the legacy OpenRouter path.

    ``laya`` selects a local server instead of a hosted provider. It is a
    replacement for the hosted pair, not a third member of it.
    """
    selected = (value or os.environ.get("JEV_PROVIDER_MODE", "openrouter")).strip().lower()
    if selected not in PROVIDER_MODES:
        raise JevClientError(
            f"JEV_PROVIDER_MODE must be one of: {', '.join(sorted(PROVIDER_MODES))}"
        )
    return selected


def validate_fallback_order(names: Any) -> tuple[str, ...]:
    """Return an ordered provider chain, rejecting anything that is not hosted.

    A local Laya route cannot appear here: it replaces the hosted providers
    rather than being tried after one of them fails, and it has no key to
    authenticate a fallback hop.
    """
    order = tuple(names)
    for name in order:
        if name not in HOSTED_PROVIDER_MODES:
            raise JevClientError(
                f"invalid Jev fallback order: {name!r} is not a hosted Jev provider; "
                "Laya runs locally in place of the hosted providers instead of joining them"
            )
    return order


def provider_order(mode: str) -> tuple[str, ...]:
    """The providers a mode uses, in the order it tries them.

    A pinned hosted mode is one provider, a chained hosted mode is two, and the
    local mode is exactly one: itself. No hosted mode ever yields the local
    route, so selecting a key never reaches a local server by accident.
    """
    if mode == LAYA_PROVIDER:
        return (LAYA_PROVIDER,)
    return validate_fallback_order(FALLBACK_ORDER.get(mode, (mode,)))


def validate_laya_endpoint(url: str) -> str:
    """A keyless local route is plain HTTP on loopback, or HTTPS anywhere else.

    The local provider sends no credential, so a plain HTTP request to another
    host would put the reviewed state on the wire unauthenticated and
    unencrypted. Loopback is the only place that is safe, and the only place
    `laya-serve` is meant to listen.
    """
    if urlsplit(url).scheme == "https":
        return url
    host = (urlsplit(url).hostname or "").lower()
    if urlsplit(url).scheme == "http" and host in _LOOPBACK_HOSTS:
        return url
    raise JevClientError(
        f"invalid local Laya endpoint {url!r}: plain HTTP is accepted on loopback only; "
        "use HTTPS for any other host"
    )


def laya_key(environ: Mapping[str, str] | None = None) -> str:
    """The optional bearer a local server was started with. Usually empty.

    ``laya-serve`` needs no credential by default, so an empty value means
    "configured without one" rather than "disabled": the header is then omitted
    entirely instead of being sent as an empty bearer.
    """
    env = os.environ if environ is None else environ
    return (env.get("LAYA_API_KEY") or "").strip()


def laya_route(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    """The local server URL and checkpoint, which are settings rather than secrets."""
    env = os.environ if environ is None else environ
    base = (env.get("JEV_LAYA_BASE_URL") or LAYA_BASE_URL_DEFAULT).strip().rstrip("/")
    path = (env.get("JEV_LAYA_ENDPOINT_PATH") or LAYA_ENDPOINT_PATH_DEFAULT).strip()
    model = (env.get("JEV_LAYA_MODEL") or LAYA_MODEL_DEFAULT).strip()
    return validate_laya_endpoint(f"{base}/{path.lstrip('/')}"), model


def validate_laya_questions(questions: dict[str, Any]) -> dict[str, Any]:
    """Reject a question the local route can only answer on the wrong scale.

    A local score question derives its legend from ``criteria`` as an ordered
    list of level descriptions, index 0 first, and answers with the expected
    level on that index scale. A dict has no order to index and the server
    refuses the request, so the check happens here rather than as a 500.
    """
    for name, question in questions.items():
        if not isinstance(question, dict) or question.get("type") != "score":
            continue
        criteria = question.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise JevSchemaError(
                f"question {name!r}: a local score question takes 'criteria' as a list of "
                "level descriptions, index 0 first; a dict has no level order to index"
            )
    return questions


def validate_laya_answers(answers: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
    """A local score stays on the legend index scale the question's levels define.

    The hosted route returns the expected level on the same index scale, so a
    value outside ``0..len(criteria)-1`` means the answer is on a different
    scale than the thresholds in ``approval_policy`` were written against, and
    the caller must not compare it to them.
    """
    for name, question in questions.items():
        if not isinstance(question, dict) or question.get("type") != "score":
            continue
        answer = answers.get(name)
        if not isinstance(answer, dict):
            continue
        criteria = question.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise JevSchemaError(
                f"question {name!r}: a local score question takes 'criteria' as a list of "
                "level descriptions, index 0 first"
            )
        value = answer.get("score")
        if not _finite(value):
            raise JevSchemaError(f"answer {name!r} has invalid score")
        top = len(criteria) - 1
        if not 0 <= float(value) <= top:
            raise JevSchemaError(
                f"answer {name!r} scored {float(value)} outside the {len(criteria)} level local scale 0..{top}"
            )
        legend = answer.get("legend")
        if legend is not None and legend != {str(index): text for index, text in enumerate(criteria)}:
            raise JevSchemaError(
                f"answer {name!r} legend does not match the level descriptions it was asked about"
            )
    return answers


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_answers(answers: Any, questions: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(answers, dict):
        raise JevSchemaError("Jev response answers must be an object")
    missing = [name for name in questions if name not in answers]
    if missing:
        raise JevSchemaError(f"Jev response omitted answers: {', '.join(missing)}")
    for name, answer in answers.items():
        if not isinstance(answer, dict):
            raise JevSchemaError(f"answer {name!r} must be an object")
        kind = questions.get(name, {}).get("type") if isinstance(questions.get(name), dict) else None
        if kind == "noul":
            value = answer.get("noul")
            if not _finite(value) or not 0 <= float(value) <= 1:
                raise JevSchemaError(f"answer {name!r} has invalid noul probability")
        elif kind == "score":
            value = answer.get("score")
            if not _finite(value):
                raise JevSchemaError(f"answer {name!r} has invalid score")
        elif kind == "choice":
            value = answer.get("choice")
            if not isinstance(value, str) or value not in questions[name].get("criteria", {}):
                raise JevSchemaError(f"answer {name!r} has an unknown choice")
        confidence = answer.get("confidence")
        if confidence is not None and (not _finite(confidence) or not 0 <= float(confidence) <= 1):
            raise JevSchemaError(f"answer {name!r} has invalid confidence")
    return answers


def request_decisions(
    state: Any,
    questions: dict[str, Any],
    api_key: str | None = None,
    *,
    model: str = MODEL,
    timeout: float = 30.0,
    transport: Callable[..., Any] | None = None,
    provider: str | None = None,
    fallback_api_key: str | None = None,
) -> dict[str, Any]:
    if not isinstance(questions, dict) or not questions:
        raise JevSchemaError("questions must be a non-empty object")
    mode = provider_mode(provider)
    local = mode in KEYLESS_PROVIDERS
    if local and fallback_api_key:
        raise JevClientError(
            "JEV_PROVIDER_MODE=laya answers from a local server in place of the hosted "
            "providers, so there is no hosted fallback to authenticate"
        )
    if local:
        validate_laya_questions(questions)
    route_model = laya_route()[1] if local else model
    local_key = laya_key() if local else (api_key or "")
    if transport is not None:
        if not local and (not api_key or not isinstance(api_key, str)):
            raise JevClientError("an API key is required for Jev reviews")
        payload = {"model": route_model, "state": state, "questions": questions}
        response = transport(payload, api_key=local_key, timeout=timeout)
        if not isinstance(response, dict):
            raise JevSchemaError("transport returned a non-object")
        answers = validate_answers(response.get("answers"), questions)
        if local:
            validate_laya_answers(answers, questions)
        return {**response, "answers": answers}
    routes: list[tuple[str, str, str, str]] = []
    for index, name in enumerate(provider_order(mode)):
        if name in KEYLESS_PROVIDERS:
            key = laya_key()
        else:
            key = api_key if index == 0 else fallback_api_key
        if name == LAYA_PROVIDER:
            endpoint, route_model = laya_route()
        elif name == TYPESAFE_PROVIDER:
            endpoint, route_model = TYPESAFE_ENDPOINT, TYPESAFE_MODEL
        else:
            endpoint, route_model = ENDPOINT, model
        routes.append((name, endpoint, route_model, key or ""))
    errors: list[str] = []
    for name, endpoint, route_model, route_key in routes:
        if not route_key and name not in KEYLESS_PROVIDERS:
            errors.append(f"{endpoint}: missing API key")
            continue
        try:
            result = _request_once(state, questions, route_key, endpoint, route_model, timeout)
        except JevClientError as exc:
            errors.append(str(exc))
            if len(routes) == 1:
                raise
            continue
        if name in KEYLESS_PROVIDERS:
            answers = result.get("answers")
            if isinstance(answers, dict):
                validate_laya_answers(answers, questions)
        return result
    raise JevClientError("; ".join(errors))


def _request_once(state: Any, questions: dict[str, Any], api_key: str,
                  endpoint: str, model: str, timeout: float) -> dict[str, Any]:
    payload = {"model": model, "state": state, "questions": questions}
    body = json.dumps(payload).encode("utf-8")
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0: break
        headers = {"Content-Type": "application/json"}
        # A keyless provider bound to the local machine carries no credential, so
        # the header is omitted entirely rather than sent as an empty bearer.
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if endpoint == ENDPOINT:
            headers.update({"HTTP-Referer": "https://hermes-agent.nousresearch.com", "X-Title": "Hermes Jev Decision Adapter"})
        request = Request(endpoint, data=body, method="POST", headers=headers)
        try:
            with urlopen(request, timeout=remaining) as response:
                result = json.loads(response.read().decode("utf-8"))
            result["answers"] = validate_answers(result.get("answers"), questions)
            return result
        except HTTPError as exc:
            last = exc
            if exc.code not in _RETRYABLE or attempt == 2:
                raise JevClientError(f"{endpoint} HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError, JevSchemaError) as exc:
            last = exc
            if isinstance(exc, JevSchemaError) or attempt == 2:
                raise JevClientError(str(exc)) from exc
        time.sleep(min(2**attempt, max(0.0, deadline - time.monotonic())))
    raise JevClientError(f"{endpoint} request failed: {last}")
