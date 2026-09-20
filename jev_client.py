"""Shared bounded client for TypeSafe Jev with OpenRouter routing."""
from __future__ import annotations

import json
import math
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
TYPESAFE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODEL = "jev-1.13.0"
PROVIDER_MODES = frozenset({
    "typesafe", "openrouter", "typesafe_then_openrouter", "openrouter_then_typesafe",
})
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


class JevClientError(RuntimeError):
    """Base error for unavailable or invalid Jev responses."""


class JevSchemaError(JevClientError):
    """The provider returned a response outside the typed contract."""


def provider_mode(value: str | None = None) -> str:
    """Return the selected route, defaulting to the legacy OpenRouter path."""
    selected = (value or __import__("os").environ.get("JEV_PROVIDER_MODE", "openrouter")).strip().lower()
    if selected not in PROVIDER_MODES:
        raise JevClientError(
            f"JEV_PROVIDER_MODE must be one of: {', '.join(sorted(PROVIDER_MODES))}"
        )
    return selected


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
    if transport is not None:
        if not api_key or not isinstance(api_key, str):
            raise JevClientError("an API key is required for Jev reviews")
        payload = {"model": model, "state": state, "questions": questions}
        response = transport(payload, api_key=api_key, timeout=timeout)
        if not isinstance(response, dict):
            raise JevSchemaError("transport returned a non-object")
        return {**response, "answers": validate_answers(response.get("answers"), questions)}
    mode = provider_mode(provider)
    if mode == "typesafe": routes = [(TYPESAFE_ENDPOINT, TYPESAFE_MODEL, api_key)]
    elif mode == "openrouter": routes = [(ENDPOINT, model, api_key)]
    elif mode == "typesafe_then_openrouter": routes = [(TYPESAFE_ENDPOINT, TYPESAFE_MODEL, api_key), (ENDPOINT, model, fallback_api_key)]
    else: routes = [(ENDPOINT, model, api_key), (TYPESAFE_ENDPOINT, TYPESAFE_MODEL, fallback_api_key)]
    errors: list[str] = []
    for endpoint, route_model, route_key in routes:
        if not route_key:
            errors.append(f"{endpoint}: missing API key")
            continue
        try:
            return _request_once(state, questions, route_key, endpoint, route_model, timeout)
        except JevClientError as exc:
            errors.append(str(exc))
            if len(routes) == 1:
                raise
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
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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
