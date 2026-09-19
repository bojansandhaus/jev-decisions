# Jev Decisions for Hermes (and other AI agents)

[![CI](https://github.com/bojansandhaus/jev-decisions/actions/workflows/ci.yml/badge.svg)](https://github.com/bojansandhaus/jev-decisions/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)

Jev Decisions is a small safety layer for AI agents. It helps an agent decide whether to act, ask for approval, wait for proof, or stop before it changes something.

It works as a **Hermes plugin** and as a **standalone Python or command line tool** for other AI agents, automation scripts, and agent frameworks.

## The use case in one minute

An AI agent can read a request, choose a tool, and report success too quickly. Jev Decisions adds a second opinion and a firm local check:

```text
Agent sees a task
        ↓
Jev asks: what is the risk, and is the evidence enough?
        ↓
Local safety rules choose: observe, suggest, or ask a human
        ↓
The agent acts only when its own authority allows it
        ↓
The exact target is read back and checked
```

Examples:

- Before deleting a backup, require human approval.
- Before restarting a service, check whether the action is reversible.
- After sending a message, check the actual delivery result instead of trusting a success claim.
- Before saving a memory, check whether it is useful, sensitive, or already known.
- Before sending an answer, check whether it answers the question and stays grounded in evidence.
- When an agent keeps revisiting the same choice, identify the next concrete step.

Jev Decisions does not run actions on its own. It gives the agent a recommendation and keeps the final authority in ordinary code and human approval.

## Why use it?

Use Jev Decisions when your AI agent can:

- call tools or APIs,
- change files, services, or online records,
- send messages,
- save memories,
- make purchases or recommendations,
- work with private information,
- claim that a task is complete.

The project gives those moments a shared safety language. The same checks can sit behind Hermes, a Python agent, a shell script, an MCP tool, or another agent framework.

## Install in Hermes

```bash
git clone https://github.com/bojansandhaus/jev-decisions.git \
  ~/.hermes/plugins/jev-decisions

hermes plugins enable jev-decisions
hermes plugins doctor jev-decisions
```

Restart Hermes after installing or changing the plugin. The plugin adds five tools and three review hooks without changing Hermes core.

Set the provider key through Hermes secret management or your environment. Keep it outside the repository:

```bash
export OPENROUTER_API_KEY="your-key"
```

The default provider settings are:

```text
Endpoint: https://openrouter.ai/api/alpha/decisions
Model:    typesafe/jev-1.13
```

## Use with another AI agent

The safety checks do not depend on Hermes. Install the project in a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
```

Ask whether an action should need a human:

```bash
jev-gateway decide <<'JSON'
{"action":"delete_backup","external":true}
JSON
```

The command returns a structured answer like this:

```json
{
  "authority": "deterministic_policy",
  "decision": "human",
  "reason": {
    "credential": false,
    "destructive": true,
    "external": true,
    "reversible": true
  }
}
```

Check whether a change is actually proven:

```bash
jev-gateway verify <<'JSON'
{"changed":true,"read_back":false,"evidence":false}
JSON
```

The result tells the agent to read the exact target back before calling the change complete:

```json
{
  "authority": "deterministic_verification",
  "next": "read_back",
  "verified": false
}
```

Python agents can call the same boundary directly:

```python
from gateway import decide, verify

policy = decide({
    "action": "restart_service",
    "external": True,
    "reversible": True,
})

if policy["decision"] == "human":
    raise RuntimeError("Human approval is required")

# The host agent performs its approved action here.
result = verify({
    "changed": True,
    "read_back": True,
    "evidence": True,
})

assert result["verified"] is True
```

The host agent remains responsible for credentials, permissions, retries, tool execution, and user approval. Jev Decisions supplies the decision check and the proof check.

See [docs/integrations.md](docs/integrations.md) for Python, shell, service, MCP, and other agent integrations.

## Hermes tools

| Tool | Plain-English purpose |
| --- | --- |
| `jev_decide` | Ask a clear yes or no question, choose between options, or give a score. |
| `jev_workflow` | Run a ready-made review for a common agent situation. |
| `jev_gateway` | Check whether an action needs approval and whether a result is proven. |
| `jev_ingest` | Turn an event from another system into a reviewable case. |
| `jev_ledger` | Record reviews and outcomes without storing private conversation text. |

### Hermes review hooks

| Hook | What it checks |
| --- | --- |
| `pre_tool_call` | Whether a planned tool call looks risky and how much checking it needs. |
| `post_tool_call` | Whether the tool result proves that the requested change worked. |
| `post_llm_call` | Whether an answer is grounded, complete, useful, and moving forward. |

These hooks observe and record recommendations. They do not secretly approve, deny, rewrite, or execute anything.

## Common use cases

### Safer tool use

Before an agent changes a server, file, service, device, or online record, review the risk. Destructive, credential related, or hard to reverse actions require a human.

### Proof after an action

A tool saying “success” is not proof. Read the exact target back. Check the result. Record what happened.

### Better answers

Review an answer before it reaches the user. Check that it uses the supplied evidence, answers every requested part, and gives a concrete next step when one is needed.

### Memory review

Before saving information, check whether it is useful later, sensitive, redundant, or in conflict with existing memory.

### Research and evidence

Classify a claim as observed, inferred, assumed, unverified, or contradicted. Ask for stronger evidence when the claim matters.

### Communication review

Before sending an email or message, check the recipient, commitment, sensitive information, and whether the draft is ready to send.

### Infrastructure and home automation

Review service changes, backups, restores, alerts, Home Assistant events, and other operations through the same action and verification rules.

### Decisions and comparisons

Compare options, rank candidates, review purchases, or referee multiple agent answers without allowing the model to perform the final action.

## Ready-made reviews

The plugin includes 25 reusable reviews:

| Area | Reviews |
| --- | --- |
| Goals and answers | `goal_judge`, `output_review`, `next_action`, `decision_circling`, `plan_review` |
| Tools and actions | `command_review`, `action_verify`, `tool_result_verify`, `verification_depth`, `escalation` |
| Memory and evidence | `memory_gate`, `memory_review`, `memory_maintenance`, `recall_rerank`, `claim_status`, `evidence_review` |
| Choices | `agent_referee`, `option_select`, `purchase_review` |
| Operations | `anomaly_review`, `daily_anomaly`, `infrastructure_review`, `document_quality` |
| Communication | `communication_review`, `promotion_review` |

These reviews accept bounded information. They do not require separate connectors for every service or domain.

## How the questions work

A Jev question has a type, clear instructions, and definitions for the possible answers.

```json
{
  "state": {
    "action": "send_email",
    "external": true,
    "creates_commitment": true
  },
  "questions": {
    "ready": {
      "type": "noul",
      "instructions": "Is this message ready to send?",
      "criteria": {
        "true": "The recipient, commitment, and facts are clear",
        "false": "Something important needs review first"
      }
    },
    "recommendation": {
      "type": "choice",
      "instructions": "What should happen next?",
      "criteria": {
        "send": "Send it",
        "revise": "Revise it first",
        "ask": "Ask one clarifying question",
        "hold": "Do not send yet"
      }
    }
  }
}
```

The three question types are:

- **Noul:** yes or no, with a confidence estimate.
- **Choice:** one option from a named list.
- **Score:** a position on an ordered scale.

The answer is structured data. Your agent decides what to do with it.

## Safety rules

The local gateway returns one of three policy decisions:

- `observe`: no outside change is involved.
- `suggest`: a reversible outside action may be proposed.
- `human`: approval is required.

After a change, verification returns:

- `done`: the available proof is enough.
- `read_back`: inspect the exact target.
- `inspect_evidence`: examine logs or another direct source of proof.

A model answer never overrides these checks. A missing provider, timeout, malformed answer, or unclear result is not permission to act.

## Privacy

Send the smallest amount of information needed for the question. Do not send credentials, private messages, full archives, or unrelated personal information.

Never commit:

- API keys, tokens, passwords, or secret files
- private conversations, sessions, memories, or local logs
- personal addresses, identifiers, or case records
- caches, bytecode, or machine specific settings

Run the public scan before every release:

```bash
python3 tools/public_scan.py
```

Read [SECURITY.md](SECURITY.md) for the complete security policy.

## Local records and calibration

The ledger stores structured review and outcome metadata so you can measure whether a review is useful. It is not a transcript store.

Keep the system advisory while you collect labeled outcomes. Promote one narrow review at a time only when your own results show that the fallback remains safe.

## Development

```bash
python3 -m pip install -e '.[test]'
python3 -m pytest -q
python3 -m compileall -q .
python3 tools/public_scan.py
```

The test suite makes no network request. A live provider test is optional and must use a key outside the repository.

## Answers to common questions

### What is Jev Decisions?

Jev Decisions is a safety and verification layer for AI agents. It helps an agent decide when to act, when to ask a human, and how to check that an action really worked.

### Does it work with Hermes?

Yes. It is packaged as a Hermes plugin with five tools and three advisory hooks.

### Does it work with other AI agents?

Yes. The local policy and verification gateway works from Python, the shell, a service, or another agent framework. Only the plugin registration layer is Hermes specific.

### Does it execute actions?

No. The host agent performs actions. Jev Decisions reviews the proposed action and checks the evidence afterward.

### Does it replace human approval?

No. Destructive, credential related, unclear, or difficult to reverse actions remain subject to human approval.

### Does it store my conversations?

The public project is designed to store structured metadata, not raw conversation text. Your host agent controls what state is sent to the provider.

### Which provider does the Hermes plugin use?

The default is OpenRouter's Decisions API with `typesafe/jev-1.13`. Other agent frameworks can use the local gateway with their own provider or model.

## Repository layout

```text
jev-decisions/
├── __init__.py       Hermes plugin and review definitions
├── gateway.py        Local action and verification rules
├── ledger.py         Local structured records
├── ingest.py         Event classification
├── fabric.py         Case queue
├── jev_gateway.py    JSON command line gateway
├── shadow_report.py  Review and calibration report
├── plugin.yaml       Hermes manifest
├── runtime.py        Hermes and standalone runtime bridge
├── tools/            Public safety scanner
├── tests/            Generic tests
├── docs/             Integration guidance
└── pyproject.toml    Python package and CLI metadata
```

## License

MIT. Copyright (c) 2026 Bojan Sandhaus. See [LICENSE](LICENSE).
