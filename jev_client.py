"""Shared bounded client for OpenRouter's typed Jev Decisions endpoint."""
from __future__ import annotations

import json
import math
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


class JevClientError(RuntimeError):
    """Base error for unavailable or invalid Jev responses."""


class JevSchemaError(JevClientError):
    """The provider returned a response outside the typed contract."""


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
    api_key: str,
    *,
    model: str = MODEL,
    timeout: float = 30.0,
    transport: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not api_key or not isinstance(api_key, str):
        raise JevClientError("OPENROUTER_API_KEY is required for Jev reviews")
    if not isinstance(questions, dict) or not questions:
        raise JevSchemaError("questions must be a non-empty object")
    payload = {"model": model, "state": state, "questions": questions}
    body = json.dumps(payload).encode("utf-8")
    if transport is not None:
        response = transport(payload, api_key=api_key, timeout=timeout)
        if not isinstance(response, dict):
            raise JevSchemaError("transport returned a non-object")
        return {**response, "answers": validate_answers(response.get("answers"), questions)}
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        request = Request(ENDPOINT, data=body, method="POST", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hermes-agent.nousresearch.com",
            "X-Title": "Hermes Jev Decision Adapter",
        })
        try:
            with urlopen(request, timeout=remaining) as response:
                result = json.loads(response.read().decode("utf-8"))
            result["answers"] = validate_answers(result.get("answers"), questions)
            return result
        except HTTPError as exc:
            last = exc
            if exc.code not in _RETRYABLE or attempt == 2:
                raise JevClientError(f"OpenRouter Jev HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError, JevSchemaError) as exc:
            last = exc
            if isinstance(exc, JevSchemaError) or attempt == 2:
                raise JevClientError(str(exc)) from exc
        time.sleep(min(2**attempt, max(0.0, deadline - time.monotonic())))
    raise JevClientError(f"OpenRouter Jev request failed: {last}")
