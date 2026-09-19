# Jev Decisions

### Typed model judgments, deterministic authority

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)

Jev Decisions gives Hermes a disciplined judgment layer for bounded questions. Jev can classify risk, compare options, inspect evidence, and review output. It cannot execute what it recommends.

The design is simple:

```text
bounded state
     │
     ▼
 typed Jev judgment  ───────►  recommendation
     │                                  │
     ▼                                  ▼
 deterministic policy  ◄──────  human confirmation
     │
     ▼
 verified action or explicit hold
```

The model is the judge. Code remains the authority.

## Why this exists

Agents fail in two opposite ways. They can act too quickly on weak evidence, or keep analyzing after the next step is already clear. Jev adds small, typed judgments at those seams:

- Is the result complete?
- Is this action safe to suggest?
- Does the evidence prove success?
- Is the draft grounded and actionable?
- Is the conversation circling a settled choice?
- Should the system ask a human, wait for evidence, or act now?

Every judgment is bounded. Every consequential action still passes through deterministic policy and verification.

## What you get

### Five Hermes tools

| Tool | Purpose |
| --- | --- |
| `jev_decide` | Run a custom typed Noul, Choice, or Score judgment. |
| `jev_workflow` | Run a reusable workflow from the catalog. |
| `jev_gateway` | Apply deterministic policy and verification rules. |
| `jev_ingest` | Turn a bounded event from another system into a classified Jev case. |
| `jev_ledger` | Record structured reviews, outcomes, commitments, decisions, and metrics locally. |

### Three advisory hooks

| Hook | Review |
| --- | --- |
| `pre_tool_call` | Prospective tool risk and verification depth. |
| `post_tool_call` | Whether the returned evidence proves success. |
| `post_llm_call` | Grounding, completeness, actionability, risk, and decision circling. |

Hooks run in shadow mode. They observe and record. They do not block, rewrite, approve, deny, or execute.

## Workflow catalog

The plugin contains 25 reusable workflows:

| Area | Workflows |
| --- | --- |
| Output and progress | `goal_judge`, `output_review`, `next_action`, `decision_circling`, `plan_review` |
| Tools and actions | `command_review`, `action_verify`, `tool_result_verify`, `verification_depth`, `escalation` |
| Memory and evidence | `memory_gate`, `memory_review`, `memory_maintenance`, `recall_rerank`, `claim_status`, `evidence_review` |
| Comparison and choice | `agent_referee`, `option_select`, `purchase_review` |
| Operations | `anomaly_review`, `daily_anomaly`, `infrastructure_review`, `document_quality` |
| Communication and promotion | `communication_review`, `promotion_review` |

These are decision classes, not hard coded integrations. Home Assistant, infrastructure, document systems, research, communication, purchasing, and personal workflows can pass bounded state through the same boundary.

## Typed questions

Jev accepts a map of named questions. Each question declares its type, instructions, and criteria.

```json
{
  "state": {
    "action": "restart_service",
    "external": true,
    "reversible": true
  },
  "questions": {
    "risk": {
      "type": "choice",
      "instructions": "What is the operational risk?",
      "criteria": {
        "low": "Read only or easily reversible",
        "medium": "Recoverable service or file change",
        "high": "Destructive, credential related, or broad outage risk"
      }
    },
    "needs_human": {
      "type": "noul",
      "instructions": "Should a human confirm before execution?",
      "criteria": {
        "true": "Authority or safety is materially uncertain",
        "false": "The action is clear, authorized, reversible, and verified"
      }
    }
  }
}
```

### The three primitives

- **Noul** returns a true or false probability.
- **Choice** selects from named options and may include probabilities and confidence.
- **Score** places the state on an ordered rubric.

Jev returns structured answers. The adapter does not ask Jev for prose.

## Deterministic authority

The gateway is deliberately stricter than the model:

```python
from gateway import decide, verify

policy = decide({
    "action": "restart_service",
    "external": True,
    "reversible": True,
})
# policy["decision"] == "suggest"

check = verify({
    "changed": True,
    "read_back": False,
    "evidence": False,
})
# check["next"] == "read_back"
```

Policy outcomes are:

- `observe`, no external effect is present
- `suggest`, a reversible external action may be proposed
- `human`, confirmation is required

Verification outcomes are:

- `done`, no further proof is required
- `read_back`, inspect the exact target
- `inspect_evidence`, examine logs or equivalent direct evidence

The gateway never runs the requested operation.

## Install in Hermes

Clone the repository into the user plugin directory, then enable it:

```bash
git clone https://github.com/bojansandhaus/jev-decisions.git \
  ~/.hermes/plugins/jev-decisions

hermes plugins enable jev-decisions
hermes plugins doctor jev-decisions
```

Restart Hermes after changing plugin code. The manifest registers the `jev` toolset, four tools, and three hooks without modifying Hermes core.

## Configuration

Keep credentials outside the repository:

```bash
# configure OPENROUTER_API_KEY outside this repository
export JEV_HOME="$HOME/.jev"
```

Hermes installations can resolve `OPENROUTER_API_KEY` through the Hermes secret scope. Standalone use reads the environment. Never place a real key in source, tests, issues, fixtures, or commit history.

The current provider contract is:

```text
Endpoint: https://openrouter.ai/api/alpha/decisions
Model:    typesafe/jev-1.13
```

Provider responses may contain a versioned model identifier. Treat that value as metadata, not as permission to act.

## JSON gateway for other systems

The gateway can be used without Hermes:

```bash
printf '%s\n' '{"external":true,"reversible":true}' \
  | python3 jev_gateway.py decide

printf '%s\n' '{"changed":true,"read_back":false,"evidence":false}' \
  | python3 jev_gateway.py verify

python3 jev_gateway.py snapshot
```

This makes the policy boundary reusable from Home Assistant automations, infrastructure scripts, document workflows, research tooling, and other agents.

## Shadow mode and calibration

The default operating mode is advisory:

1. Hermes calls Jev with bounded, redacted state.
2. Jev returns typed answers.
3. The plugin writes structured metadata and hashes.
4. Deterministic policy decides whether execution is possible.
5. A human or direct read back establishes the outcome.
6. The ledger can record whether the judgment was correct.

The ledger intentionally excludes raw prompts, drafts, tool arguments, tool results, credentials, and private conversation history. Promotion beyond shadow mode should happen one narrow workflow at a time, after labeled outcomes show that the fallback remains safe.

## Privacy and public repository rules

This repository contains code, generic fixtures, and documentation only. It does not contain:

- API keys, tokens, passwords, or secret files
- Hermes sessions, logs, memory, or local calibration records
- personal names, addresses, identifiers, or private case data
- generated bytecode, caches, or machine specific configuration

Run the public scan before every push:

```bash
python3 tools/public_scan.py
```

## Development

```bash
python3 -m pytest -q
python3 -m compileall -q .
python3 tools/public_scan.py
```

For a live provider check, supply the key through the environment and run your own bounded fixture. The normal test suite makes no network request.

## Repository layout

```text
jev-decisions/
├── __init__.py             Hermes plugin entrypoint and typed workflows
├── gateway.py              Deterministic policy and verification
├── ledger.py               Append only structured local records
├── ingest.py               Cross system event classification
├── fabric.py               Jev case queue
├── jev_gateway.py          JSON stdin gateway
├── shadow_report.py        Review and calibration report
├── plugin.yaml             Hermes manifest
├── runtime.py              Hermes or standalone runtime bridge
├── tools/
│   ├── public_scan.py      Public safety scan
├── tests/
├── docs/
└── pyproject.toml
```

## Design principles

1. Keep model judgments typed and bounded.
2. Keep execution authority deterministic.
3. Require human authority for destructive or uncertain actions.
4. Verify state changes against the exact target.
5. Store structured evidence, not private raw content.
6. Promote narrow workflows only after labeled evaluation.
7. Keep the public project free of local state.

## License

MIT. See [LICENSE](LICENSE).
