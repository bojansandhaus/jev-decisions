# Jev Decisions: Technical reference

Installation for other agents, tool names, review definitions, and executable examples. Start with the [product README](../README.md) for Hermes setup and everyday use.

### Install the standalone Python and CLI gateway

Use a separate virtual environment:

```bash
git clone https://github.com/bojansandhaus/jev-decisions.git
cd jev-decisions
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1` instead. The examples below use a POSIX shell.

Standalone installation provides the local gateway, CLI, and supporting Python modules. Hermes loads its registration layer separately; deployment specific collectors are not included.

This installs the `jev-gateway` command. It evaluates JSON supplied by your runner; it does not launch another agent or connect to your services. There is no need to configure OpenRouter for local `decide` and `verify` calls.


### In the terminal: check policy, then evidence

```bash
printf '%s\n' '{"action":"delete_backup","external":true,"reversible":false,"destructive":true,"credential":false}' | jev-gateway decide
```

Inspect the `decision` field. A destructive operation requires `human` regardless of a model's opinion.

Now describe a changed target that has not been checked:

```bash
printf '%s\n' '{"changed":true,"read_back":false,"evidence":false}' | jev-gateway verify
```

The verification result should contain `"verified": false` and `"next": "read_back"`. Missing or non-boolean change evidence returns `establish_change`; a readback without evidence returns `inspect_evidence`. The gateway requires all three proof fields to be the boolean `true` before returning `done`.

After your agent actually reads the exact target and confirms the requested result, it can submit:

```bash
printf '%s\n' '{"changed":true,"read_back":true,"evidence":true}' | jev-gateway verify
```

The result should contain `"verified": true` and `"next": "done"`. These inputs are deliberately simple fixtures. In a real integration, derive them from observed results. Setting them to `true` without checking anything defeats the purpose.


## Hermes tools and hooks

The plugin exposes six tools under the `jev` toolset.

<table>
<tr><th>Tool</th><th>Use it for</th><th>Provider required?</th></tr>
<tr><td><code>jev_decide</code></td><td>Custom typed questions against bounded state.</td><td>Yes</td></tr>
<tr><td><code>jev_workflow</code></td><td>A prepared review such as <code>plan_review</code>, <code>output_review</code>, or the opt in <code>approval_review</code>.</td><td>Yes</td></tr>
<tr><td><code>jev_gateway</code></td><td>Local action policy, verification, domain classification, and ledger snapshot.</td><td>No</td></tr>
<tr><td><code>jev_ingest</code></td><td>Open a rule classified case from supplied event data.</td><td>No</td></tr>
<tr><td><code>jev_ledger</code></td><td>Record reviews, labeled outcomes, commitments, and decisions; inspect metrics.</td><td>No</td></tr>
<tr><td><code>jev_loop</code></td><td>Link decisions, observations, and outcomes; assess the resulting history.</td><td>No</td></tr>
</table>

The `approval_review` workflow is an opt in advisory check for flagged commands. It returns typed answers and a deterministic applied rule; it never authorizes execution. Configure the optional provider through [the approval guide](approvals.md).

Three optional hooks observe the agent lifecycle when `JEV_ENABLE_HOOKS` is enabled:

- `pre_tool_call` reviews proposed tool use.
- `post_tool_call` reviews the returned result.
- `post_llm_call` reviews the answer against the supplied request and context.

Optional platform event handlers can also record event metadata for Home Assistant, email, Telegram, Discord, Matrix, and DingTalk when the host exposes the required adapter API. They do not send messages or control those services. This is an integration surface, not a guarantee that every platform version has been tested.

Hooks return no approval, replacement answer, or execution instruction. They may record local review data. Model reviews can add provider requests and latency when enabled; see the configuration and privacy details in [the integration guide](integrations.md).

## Tool actions and records

### Local policy: `jev_gateway`

- `decide`: apply local rules to `state`. Destructive actions, credential changes, and irreversible external actions recommend `human`; other external actions recommend `suggest`; internal work recommends `observe`.
- `verify`: require explicit boolean `changed`, `read_back`, and `evidence` fields. Missing or invalid proof cannot produce a verified result.
- `classify`: classify supplied `state` within a required `domain` using local rules.
- `snapshot`: return the timestamp and ledger metrics.

Use JSON booleans, never strings such as `"false"`. The policy falls back to its defaults for omitted or invalid boolean fields: `reversible` defaults to true; `external`, `destructive`, and `credential` default to false. Supply these facts explicitly and validate them in your host. The rule is not a shell command parser or an enforcement gate. The `success` field on a tool response describes the handler result, not proof that your external task succeeded. Inspect `verified` and `next` when checking evidence.

### Review ledger: `jev_ledger`

- `record_review`: create a review with `details`; `status` supplies its workflow label. Supplying an existing `review_id` returns that ID without creating another review.
- `record_outcome`: attach boolean `correct` and optional `details` to a `review_id`.
- `add_commitment` and `add_decision`: record nonempty `text`, optional `owner`, `deadline`, `status`, and `details`.
- `close`: append a closure against a `review_id`. This preserves the earlier entry.
- `list`: return the latest 200 entries.
- `metrics`: summarize recorded reviews, outcomes, labels, and record kinds. These figures describe supplied labels, not an independent benchmark of model quality.

### Decision journal: `jev_loop`

- `record_decision`: record `question`, `chosen`, optional `options`, `evidence`, `assumptions`, `owner`, and `deadline`. Keep the returned `decision_id`.
- `record_observation`: attach an `observation` and `source` to that ID. Omit `supports` when support is unknown.
- `record_outcome`: attach `status`, optional boolean `success`, `evidence`, and `notes`. Omitted success remains unknown.
- `label_outcome`: attach an explicit boolean `success`, supporting `evidence`, optional `labeler`, and `notes`. The default labeler is `user`; this field is attribution supplied by the caller, not authenticated identity.
- `reopen`: append a reason and optional evidence for revisiting a decision.
- `assess`: summarize the decision's observations and labeled outcomes, then recommend collecting an outcome, continuing observation, reviewing behavior, or reviewing new evidence.
- `list`: return recent journal rows; `limit` is clamped to 1 through 500.
- `verify_observation`: compare a supplied observation with an explicit expected value, without a provider request or journal write.

Assessment uses explicit outcome labels when present, otherwise known boolean outcomes. Unknown outcomes do not enter the success fraction. Multiple labels count separately; the fraction is descriptive, not a statistical guarantee. A reopen record continues to request review of new evidence. The journal does not train a model or change execution rules.

### Observation comparison

Call `jev_loop` with:

```json
{
  "action": "verify_observation",
  "source": "home_assistant",
  "expected": "on",
  "result": {"state": "off"}
}
```

This returns `verified: false`, `status: "mismatch"`, and `next: "read_back_expected"`. A matching `on` observation returns `matched`. Without an expected value, the next step is `compare_expected`. Python callers can use `verification.verify_observation(source, context, result)`.

The comparator trims whitespace and ignores letter case. For an object result it compares the `state` field; otherwise it compares the supplied result as text. `expected_state` and `expected_status` are aliases for `expected`. Error or timeout text produces `unavailable`. This is a small text/state comparator, not a general object validator or service health client. It does not contact a device, check timestamps, or prove that the observation belongs to the requested target. The host must establish those facts.

### Event cases: `jev_ingest`

Supply `source`, `event_type`, and a `payload` object. Ingestion routes the event to a domain, applies local classification, and returns a case ID. Python integrations can call `fabric.open_case`, `fabric.close_case`, and `fabric.queue`; queue filters accept status and domain. Tool result correlation uses invocation IDs when supplied. Supply those IDs for overlapping calls to the same tool.

## Reports and supporting commands

Only `jev-gateway` is installed as a named console command. Other packaged entry points run as Python modules:

```bash
printf '%s\n' '{}' | python3 -m jev_case list
printf '%s\n' 'I will review the draft.' | python3 -m jev_cockpit
python3 -m shadow_report
```

`jev_case` supports `open`, `close`, and `list`, reading a JSON object from stdin. Use its command help for case ID, domain, and status options. Opening and closing cases writes local records. `jev_cockpit` prints a case/ledger snapshot and, when text is supplied, candidate commitments. Detection is a simple English phrase rule; candidates are not confirmed obligations.

The Python `cockpit` module also exposes `promote_commitment`, `stale_cases`, and `digest`. Promotion writes a reviewed commitment. The other functions summarize existing records. These functions are not additional registered Hermes tools or a graphical dashboard.

`shadow_report` summarizes automatic review requests, answer probabilities, reported cost, ledger labels, and journal outcomes. Request success is not task success. Its default input is `~/.hermes/logs/jev-shadow.jsonl`; use its log path option for a named profile or standalone storage. Its help also offers JSON output. Reports depend on the records you retained and labels you supplied. Journals are append-only in normal use, but are not cryptographically tamper evident and can be changed by someone with filesystem access.

The package currently uses POSIX file locking for journal writes. Linux is exercised by CI. Native Windows is not supported by this locking implementation; use a Linux environment such as WSL rather than assuming the PowerShell activation example above establishes platform compatibility.

## Prepared review catalog

The plugin includes 25 named workflows. Supply only the context each question needs.

<details>
<summary><strong>Goals, plans, and answers</strong></summary>

- `goal_judge`: assess task completion, blockers, and result quality.
- `plan_review`: check the outcome, prerequisites, and recovery path.
- `output_review`: check grounding, coverage, actionability, and remaining risk.
- `next_action`: choose a concrete next step or identify a blocking question.
- `decision_circling`: identify repeated analysis that no longer advances a choice.

</details>

<details>
<summary><strong>Actions, authority, and verification</strong></summary>

- `command_review`: assess risk and recommend allowing, asking, or denying.
- `action_verify`: assess whether supplied evidence supports completion.
- `tool_result_verify`: review tool output and the required followup.
- `verification_depth`: choose the amount of checking an action deserves.
- `escalation`: identify uncertainty about intent, permission, risk, or evidence.

</details>

<details>
<summary><strong>Memory and evidence</strong></summary>

- `memory_gate`: review durability, type, and sensitivity.
- `memory_review`: review usefulness, type, and conflicts.
- `memory_maintenance`: recommend keeping, merging, refreshing, quarantining, or discarding.
- `recall_rerank`: review relevance and conflicts in a candidate memory set.
- `claim_status`: classify a claim as observed, inferred, assumed, unverified, or contradicted.
- `evidence_review`: assess source support, citation needs, and uncertainty.

</details>

<details>
<summary><strong>Choices, operations, and communication</strong></summary>

- `agent_referee`: compare supplied candidate outputs.
- `option_select`: compare labeled options against an objective.
- `purchase_review`: assess fit, evidence, and the next purchasing step.
- `anomaly_review`: identify unusual behavior and its severity.
- `daily_anomaly`: review a deviation from a supplied baseline.
- `infrastructure_review`: assess operational risk, backup, and verification.
- `document_quality`: review duplication, metadata, and extracted facts.
- `communication_review`: review readiness to send, commitments, and sensitive content.
- `promotion_review`: review whether evidence supports a narrower, stricter integration.

</details>

These are review definitions, not independent service connectors. For example, `document_quality` evaluates what you provide; it does not retrieve your document archive. Option selection and agent comparison use the labels defined by their questions. Use `jev_decide` when you need a different choice set.

## Custom questions

Use `jev_decide` when the prepared workflows do not fit. Each question needs a type, instructions, and criteria that define the possible answers.

- **Yes/no probability (`noul`)** returns a number from 0 to 1 for a true or false question, rather than a boolean verdict.
- **Choice** selects from named alternatives.
- **Score** evaluates against an ordered list of criteria.

Example tool arguments:

```json
{
  "state": {
    "task": "Update a test document",
    "backup_exists": true,
    "readback_planned": false
  },
  "questions": {
    "ready": {
      "type": "noul",
      "instructions": "Does the plan include a direct check of the edited document?",
      "criteria": {
        "true": "The plan includes reading and comparing the edited document",
        "false": "The plan lacks a direct comparison after editing"
      }
    },
    "next": {
      "type": "choice",
      "instructions": "What should the host do before executing this plan?",
      "criteria": {
        "proceed": "The plan covers recovery and verification",
        "revise": "Add the missing verification step",
        "ask": "Clarify a missing permission"
      }
    }
  }
}
```

Returned probabilities and confidence describe the model's judgment. They do not prove that a statement is true or that an action is authorized. Keep questions specific enough that a later observation can confirm or contradict them.

## Integrate another AI agent

Call the local gateway before a consequential operation. Branch on its result, apply your own approval rules, execute through your host, and verify using observations from the target.

```python
from gateway import decide, verify

policy = decide({
    "action": "restart_service",
    "external": True,
    "reversible": True,
    "destructive": False,
    "credential": False,
})

# A recommendation is not permission to execute.
assert policy["decision"] == "suggest"

# Your host checks authority and performs the approved action.
# This fixture represents a result that still needs a target readback.
check = verify({
    "changed": True,
    "read_back": False,
    "evidence": False,
})
assert check["verified"] is False
assert check["next"] == "read_back"
```

The Python functions and CLI can sit behind an MCP tool or HTTP service you build. This repository does not ship a universal MCP server or native adapters for every agent framework. The Hermes registration code stays specific to Hermes; your own provider can supply semantic judgment while the local gateway handles explicit policy state.

See [the integration guide](integrations.md) for the interface contract and operational details.


## Local storage

Hermes uses the active profile home. Without Hermes, storage uses `JEV_HOME`, falling back to `~/.jev`.

- `logs/jev-shadow.jsonl`: automatic review metadata and model answers.
- `logs/jev-ledger.jsonl`: reviews, outcomes, commitments, decisions, and case events.
- `logs/jev-closed-loop.jsonl`: linked decision, observation, and outcome records.

Manual entries can contain submitted text and evidence. No automatic retention policy is provided. Protect the directory, review what you store, and keep runtime files out of public repositories.

## Development and verification

From a source checkout:

```bash
python3 -m pip install -e '.[test]'
python3 -m pytest -q
python3 tools/public_scan.py
```

Run tests with isolated runtime storage. Keep live provider tests separate from deterministic CI and use synthetic inputs. A passing test suite should be followed by a clean installation check, not just an import from a working directory containing private files.

The repository separates its public plugin code from deployment specific collectors and private runtime state. [CONTRIBUTING.md](../CONTRIBUTING.md) describes contribution checks; [SECURITY.md](../SECURITY.md) explains the security boundary.
