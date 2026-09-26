"""Shared bounded client for Jev over a TypeSafe or OpenRouter key, or Laya locally.

Three arrangements for a typed question: a hosted Jev provider behind an API key,
a local `laya-serve` process that needs no key at all, or an opt in chain that
starts at the local server and falls through to one or both hosted providers.
The plain local route replaces the hosted one rather than joining the chain. Only
the `laya_then_*` modes let a failed local attempt reach a hosted provider.

Two of DOGA's three selector names are accepted as aliases for the arrangements
above: `laya_local` for the plain local mode, and `laya_with_jev_fallback` for the
local first chain that names both hosted providers. `MODE_ALIASES` holds the
mapping, and `resolve_mode` turns either vocabulary into the one canonical mode
name every code path below uses.

A local failure may reach a hosted provider only until it has failed three times
in a row. The count is per process, so a restart resets it, and any local answer
that passes validation resets it too. Past the limit the local error is re-raised
and no hosted request is made, which bounds repeated remote egress however the
mode names its hosted providers. The count tracks local failures only, so it
bounds egress identically across all four `laya_then_*` modes. It cannot detect a
valid but incorrect local answer.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

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
# Local first chains. Laya answers from the local server, and a failed local
# attempt falls through to the named hosted providers in the order given. These
# are the only modes where one review can reach both a local and a hosted route.
LAYA_CHAIN_MODES = frozenset({
    "laya_then_typesafe",
    "laya_then_openrouter",
    "laya_then_typesafe_openrouter",
    "laya_then_openrouter_typesafe",
})
PROVIDER_MODES = HOSTED_PROVIDER_MODES | LAYA_CHAIN_MODES | {LAYA_PROVIDER}
# A provider bound to the local machine carries no credential requirement, so an
# empty key means "send no Authorization header", not "disabled".
KEYLESS_PROVIDERS = frozenset({LAYA_PROVIDER})
# DOGA names three arrangements: `jev_api`, `laya_local`, and
# `laya_with_jev_fallback`. The first is the hosted arrangement this repository
# already has under its own hosted mode names, so it needs no alias. The other two
# are accepted here and resolved to a canonical mode before anything routes:
#
#   laya_local             -> laya
#   laya_with_jev_fallback -> laya_then_openrouter_typesafe
#
# The chain is spelled out rather than implied. DOGA's own Jev route tries
# OpenRouter first and direct TypeSafe second, and `openrouter` is this
# repository's default hosted provider, so the local first chain that names both
# hosted providers in that order is the faithful mapping. Nothing here is inferred
# from the alias name at request time; the table is the whole mapping.
MODE_ALIASES: dict[str, str] = {
    "laya_local": LAYA_PROVIDER,
    "laya_with_jev_fallback": "laya_then_openrouter_typesafe",
}
# Every value `JEV_PROVIDER_MODE` accepts: the canonical modes plus the aliases.
ACCEPTED_MODES = frozenset(PROVIDER_MODES | set(MODE_ALIASES))
# Consecutive local failure limit. The first three consecutive local failures in a
# process may fall through to a hosted provider; the fourth and every one after it
# re-raises the local error instead. Hardcoded, per process, and never persisted.
LOCAL_FALLBACK_FAILURE_LIMIT = 3
_local_failure_lock = threading.Lock()
_local_failure_count = 0
# The environment variable that carries each hosted provider's credential.
PROVIDER_KEY_ENV = {TYPESAFE_PROVIDER: "TYPESAFE_API_KEY", OPENROUTER_PROVIDER: "OPENROUTER_API_KEY"}
FALLBACK_ORDER: dict[str, tuple[str, ...]] = {
    "typesafe_then_openrouter": (TYPESAFE_PROVIDER, OPENROUTER_PROVIDER),
    "openrouter_then_typesafe": (OPENROUTER_PROVIDER, TYPESAFE_PROVIDER),
    "laya_then_typesafe": (LAYA_PROVIDER, TYPESAFE_PROVIDER),
    "laya_then_openrouter": (LAYA_PROVIDER, OPENROUTER_PROVIDER),
    "laya_then_typesafe_openrouter": (LAYA_PROVIDER, TYPESAFE_PROVIDER, OPENROUTER_PROVIDER),
    "laya_then_openrouter_typesafe": (LAYA_PROVIDER, OPENROUTER_PROVIDER, TYPESAFE_PROVIDER),
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


def resolve_mode(name: str) -> str:
    """The canonical mode an accepted name selects, or an error naming the accepted set.

    Two vocabularies name the same arrangements: this repository's own mode names,
    and the DOGA selector aliases in ``MODE_ALIASES``. Resolution happens once,
    here, so every code path below sees a canonical mode and no routing decision
    depends on which vocabulary the caller used.
    """
    if name in PROVIDER_MODES:
        return name
    alias = MODE_ALIASES.get(name)
    if alias is None:
        raise JevClientError(
            f"JEV_PROVIDER_MODE must be one of: {', '.join(sorted(ACCEPTED_MODES))}"
        )
    return alias


def provider_mode(value: str | None = None) -> str:
    """Return the selected route, defaulting to the legacy OpenRouter path.

    ``laya`` selects a local server instead of a hosted provider: a replacement
    for the hosted pair, not a third member of it. The ``laya_then_*`` modes are
    the opt in chains, where a failed local attempt falls through to the named
    hosted provider or providers. The DOGA aliases ``laya_local`` and
    ``laya_with_jev_fallback`` are accepted and resolve to the modes above.
    """
    selected = (value or os.environ.get("JEV_PROVIDER_MODE", "openrouter")).strip().lower()
    return resolve_mode(selected)


def validate_fallback_order(names: Any) -> tuple[str, ...]:
    """Return an ordered provider chain, rejecting any shape a mode does not name.

    A hosted chain is one or two hosted providers. A local first chain may begin
    with Laya, which is keyless, and then name the hosted providers that answer a
    failed local attempt. Laya may only be the first member: it never trails a
    hosted provider, because a local server replaces the hosted route rather than
    being tried after one of them fails. A chain alone is not a mode, so
    ``(LAYA_PROVIDER,)`` is rejected here; the plain local mode is selected by its
    own name instead.
    """
    order = tuple(names)
    if not order:
        raise JevClientError("invalid Jev fallback order: the chain is empty")
    for index, name in enumerate(order):
        if name not in PROVIDER_MODES:
            raise JevClientError(
                f"invalid Jev fallback order: {name!r} is not a Jev provider; "
                f"choose one of {', '.join(sorted(PROVIDER_MODES))}"
            )
        if name != LAYA_PROVIDER:
            continue
        if index != 0:
            raise JevClientError(
                "invalid Jev fallback order: Laya is a local provider, not a hosted Jev "
                "provider, so it cannot follow a hosted hop"
            )
        if len(order) == 1:
            raise JevClientError(
                "invalid Jev fallback order: Laya alone is a local provider, not a hosted "
                "Jev provider chain, and the plain local mode is selected by name"
            )
    if len(order) != len(set(order)):
        raise JevClientError(f"invalid Jev fallback order: {order!r} names a provider twice")
    return order


def provider_order(mode: str) -> tuple[str, ...]:
    """The providers a mode uses, in the order it tries them.

    A pinned hosted mode is one provider and a chained hosted mode is two. A
    ``laya_then_*`` mode starts at the local server and names one or both hosted
    providers after it. The plain local mode is exactly one: itself. Only a mode
    that names the local route reaches it, so selecting a hosted mode never
    contacts a local server by accident and no mode appends Laya silently. A DOGA
    alias is resolved first, so it reports the order of the mode it aliases.
    """
    mode = resolve_mode(mode)
    if mode == LAYA_PROVIDER:
        return (LAYA_PROVIDER,)
    return validate_fallback_order(FALLBACK_ORDER.get(mode, (mode,)))


def _hosted_key_names(order: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(PROVIDER_KEY_ENV[name] for name in order if name not in KEYLESS_PROVIDERS)


def provider_keys(mode: str) -> tuple[str, ...]:
    """Environment variable names for a mode's hosted providers, in chain order."""
    return _hosted_key_names(provider_order(mode))


def uses_local_hop(mode: str) -> bool:
    """True when a mode begins at the local server and needs the longer local budget."""
    return provider_order(mode)[0] in KEYLESS_PROVIDERS


def _note_local_failure() -> bool:
    """Count one consecutive local failure; True when the hosted fallback is now suppressed.

    The limit is hardcoded at three. The first three consecutive local failures may
    fall through to a hosted provider; every one after that re-raises the local
    error instead, because a local server that has failed four times in a row is
    not a transient fault and should not keep turning reviews into remote traffic.
    """
    global _local_failure_count
    with _local_failure_lock:
        _local_failure_count += 1
        return _local_failure_count > LOCAL_FALLBACK_FAILURE_LIMIT


def _reset_local_failures() -> None:
    """Restart the consecutive count after any local answer that passed validation."""
    global _local_failure_count
    with _local_failure_lock:
        _local_failure_count = 0


def local_failure_count() -> int:
    """This process's consecutive local failure count, for tests and telemetry."""
    with _local_failure_lock:
        return _local_failure_count


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
    order = provider_order(mode)
    local_first = order[0] in KEYLESS_PROVIDERS
    local = mode in KEYLESS_PROVIDERS
    if local and fallback_api_key:
        raise JevClientError(
            "JEV_PROVIDER_MODE=laya answers from a local server in place of the hosted "
            "providers, so there is no hosted fallback to authenticate"
        )
    if mode in LAYA_CHAIN_MODES:
        _require_hosted_keys(mode, order, api_key, fallback_api_key)
    if local_first:
        validate_laya_questions(questions)
    if transport is not None and mode not in LAYA_CHAIN_MODES:
        route_model = laya_route()[1] if local else model
        local_key = laya_key() if local else (api_key or "")
        if not local and (not api_key or not isinstance(api_key, str)):
            raise JevClientError("an API key is required for Jev reviews")
        payload = {"model": route_model, "state": state, "questions": questions}
        response = transport(payload, api_key=local_key, timeout=timeout)
        if not isinstance(response, dict):
            raise JevSchemaError("transport returned a non-object")
        answers = validate_answers(response.get("answers"), questions)
        if local:
            validate_laya_answers(answers, questions)
            # A local answer that passes validation is a healthy local call, so the
            # consecutive failure count restarts here.
            _reset_local_failures()
        return {**response, "answers": answers}
    routes: list[tuple[str, str, str, str]] = []
    hosted_index = 0
    for name in order:
        if name in KEYLESS_PROVIDERS:
            key = laya_key()
        else:
            key = api_key if hosted_index == 0 else fallback_api_key
            hosted_index += 1
        if name == LAYA_PROVIDER:
            endpoint, route_model = laya_route()
        elif name == TYPESAFE_PROVIDER:
            endpoint, route_model = TYPESAFE_ENDPOINT, TYPESAFE_MODEL
        else:
            endpoint, route_model = ENDPOINT, model
        routes.append((name, endpoint, route_model, key or ""))
    errors: list[str] = []
    attempts: list[dict[str, str]] = []
    for index, (name, endpoint, route_model, route_key) in enumerate(routes):
        if not route_key and name not in KEYLESS_PROVIDERS:
            message = f"{endpoint}: missing API key"
            errors.append(message)
            attempts.append({"provider": name, "error": message})
            continue
        try:
            if transport is not None:
                result = _transport_once(transport, state, questions, route_key, endpoint, route_model, timeout)
            else:
                result = _request_once(state, questions, route_key, endpoint, route_model, timeout)
        except JevClientError as exc:
            # Only a chain has a hosted hop to fall through to, so only a chain counts
            # a local failure or can suppress one. The plain local mode has neither a
            # hosted hop nor anything to suppress, so its failure leaves the count alone.
            if mode in LAYA_CHAIN_MODES and name in KEYLESS_PROVIDERS:
                if _note_local_failure():
                    # Only the exception class is logged, never the reviewed state.
                    logger.warning(
                        "local %s failed %d times in a row; hosted fallback suppressed, "
                        "re-raising the local error",
                        type(exc).__name__, LOCAL_FALLBACK_FAILURE_LIMIT,
                    )
                    raise
                logger.warning(
                    "local %s failed (%s); falling through to the hosted fallback",
                    name, type(exc).__name__,
                )
            errors.append(str(exc))
            attempts.append({"provider": name, "error": str(exc)})
            if len(routes) == 1:
                raise
            continue
        if name in KEYLESS_PROVIDERS:
            answers = result.get("answers")
            if isinstance(answers, dict):
                validate_laya_answers(answers, questions)
            # A local answer that passes validation is a healthy local call, so the
            # consecutive failure count restarts here.
            _reset_local_failures()
        return _with_routing(result, mode, routes, index, attempts)
    raise JevClientError("; ".join(errors))


def _require_hosted_keys(mode: str, order: tuple[str, ...], api_key: Any, fallback_api_key: Any) -> None:
    """Fail a ``laya_then_*`` selection when a named hosted provider has no key.

    The local attempt is allowed to fail, but only when the hosted hop it falls
    through to can actually run. A missing key is a selection error, so it is
    raised here, naming the environment variable, rather than surfacing later as a
    failed request after the local review was already sent.
    """
    keys = (api_key, fallback_api_key)
    missing = [
        name for index, name in enumerate(_hosted_key_names(order))
        if not keys[index]
    ]
    if missing:
        raise JevClientError(
            f"JEV_PROVIDER_MODE={mode} needs {', '.join(missing)} for its hosted fallback"
        )


def _transport_once(transport: Callable[..., Any], state: Any, questions: dict[str, Any],
                    api_key: str, endpoint: str, model: str, timeout: float) -> dict[str, Any]:
    """One chain hop through an injected transport, so a test can watch the route."""
    payload = {"model": model, "state": state, "questions": questions}
    response = transport(payload, api_key=api_key, timeout=timeout, endpoint=endpoint)
    if not isinstance(response, dict):
        raise JevSchemaError("transport returned a non-object")
    answers = validate_answers(response.get("answers"), questions)
    return {**response, "answers": answers}


def _with_routing(result: dict[str, Any], mode: str, routes: list[tuple[str, str, str, str]],
                  answered_index: int, attempts: list[dict[str, str]]) -> dict[str, Any]:
    """Add the routing diagnostics a ``laya_then_*`` chain has to report.

    Only the local first chains add this block, so the hosted modes and the plain
    local mode keep returning exactly the provider's own response. `provider` is
    the hop that answered, `fallback_used` says whether the successful hop was a
    fallback, and `attempts` records the earlier hops that failed.
    """
    if mode not in LAYA_CHAIN_MODES:
        return result
    return {
        **result,
        "provider_routing": {
            "provider": routes[answered_index][0],
            "provider_order": [name for name, *_ in routes],
            "fallback_used": answered_index > 0,
            "attempts": list(attempts),
        },
    }


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
