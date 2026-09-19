# Integration guide

Jev Decisions has one provider specific edge and one provider independent boundary.

The edge asks Jev a bounded question. The boundary decides what your agent may do next.

## Provider call contract

The default Hermes adapter sends this shape to OpenRouter's Decisions API:

```json
{
  "model": "typesafe/jev-1.13",
  "state": {"...": "bounded state"},
  "questions": {
    "question_id": {
      "type": "noul",
      "instructions": "A precise question",
      "criteria": {
        "true": "What true means",
        "false": "What false means"
      }
    }
  }
}
```

Keep `state` small and redacted. Put definitions in `criteria`, not in a free form prompt. Keep the question count bounded. Treat the returned answer as a recommendation.

## Adapter contract for another agent

A framework adapter only needs to do five things:

1. Build bounded state from its own context.
2. Ask a typed Jev question, or use its own provider for semantic judgment.
3. Call `gateway.decide(state)` before an external action.
4. Execute the action only under the host framework's authority rules.
5. Call `gateway.verify(result_state)` and read back the exact target.

A minimal adapter can use the deterministic boundary without making a network request:

```python
from gateway import decide, verify

state = {
    "action": "update_document",
    "external": True,
    "reversible": True,
}

policy = decide(state)
if policy["decision"] == "human":
    raise RuntimeError("Confirmation required")

# The host agent performs its own approved operation here.
result = {"changed": True, "read_back": True, "evidence": True}
assert verify(result)["verified"] is True
```

The repository does not pretend to know the permission model of every agent framework. Keep the adapter thin and let the host own credentials, tool execution, retries, and user confirmation.

## Shell and service integration

The JSON gateway is useful when an agent runs commands or communicates through a service boundary:

```bash
printf '%s\n' '{"action":"delete_backup","external":true}' \
  | jev-gateway decide

printf '%s\n' '{"changed":true,"read_back":true,"evidence":true}' \
  | jev-gateway verify
```

The JSON output is stable enough for a shell wrapper, an MCP tool, an HTTP service, or a workflow engine. Pin the project version in deployments and validate the fields you depend on.

## Redaction pattern

Before sending state to Jev, retain the facts needed for the judgment and remove the payload that does not affect it:

```python
safe_state = {
    "action": "send_email",
    "recipient_class": "external",
    "has_attachment": True,
    "creates_commitment": True,
    "body_length": 842,
}
```

Do not send the email body, access tokens, private correspondence, full memory records, or unrelated personal data unless the judgment genuinely requires them. If the content itself must be reviewed, pass the smallest excerpt that answers the typed question and apply the host's privacy controls first.

## Failure handling

A provider timeout, malformed answer, or missing key is not permission to act. Treat provider failure as an unavailable judgment and apply the host's conservative fallback:

- ask a human for consequential actions,
- wait for evidence when verification is incomplete,
- keep read only work separate from state changing work,
- record the failure without storing sensitive payloads.

## Hermes mapping

Hermes maps the integration contract onto its tool and hook system:

- `jev_decide` sends custom typed questions.
- `jev_workflow` selects a bounded workflow definition.
- `jev_gateway` applies local policy and verification.
- `jev_ingest` opens a classified case from an event.
- `jev_ledger` records structured metadata.
- The three hooks observe tool calls and model output in shadow mode.

The same boundary can sit behind another agent without importing Hermes internals. Only the plugin registration layer is Hermes specific.
