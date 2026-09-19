<div align="center">
  <h1>Jev Decisions Plugin for Hermes (and other AI Agents)</h1>
  <p><strong>Give your agent a second opinion before action, and a reason to check its work.</strong></p>
  <p>Tool risk reviews, human approval recommendations, evidence checks, and a decision journal.</p>
  <p>
    <a href="https://github.com/bojansandhaus/jev-decisions/actions/workflows/ci.yml"><img src="https://github.com/bojansandhaus/jev-decisions/actions/workflows/ci.yml/badge.svg" alt="Jev Decisions CI status"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="MIT License"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-3776AB.svg" alt="Python 3.10 or newer"></a>
  </p>
  <p>
    <a href="#quick-start">Install</a> ·
    <a href="#your-first-useful-check">Try a check</a> ·
    <a href="#what-you-can-use-it-for">Use cases</a> ·
    <a href="docs/integrations.md">Integration guide</a> ·
    <a href="#frequently-asked-questions">FAQ</a>
  </p>
</div>

**Jev Decisions Plugin for Hermes (and other AI Agents)** adds structured decision reviews to AI agent workflows. Use it to examine a proposed tool call, flag missing evidence, recommend human approval, and record what happened after a decision. Hermes gets native tools and advisory hooks. Other agents can call the local Python gateway or JSON command line interface.

A tool returning `success` tells you that a call completed. It may tell you nothing about whether the right document changed, the message reached its recipient, or the restored backup works. Jev gives those questions a place in the workflow before the agent announces that the job is done.

> [!IMPORTANT]
> Jev reviews and recommends. It does not execute your actions, block every unsafe command, grant permission, or read remote targets on its own. Your agent must enforce approval rules, collect evidence, and pass accurate state to the gateway. Hermes hooks run in advisory mode.

## What you get

- **A second opinion at the point of action.** Review risk, authority, reversibility, and the evidence an operation should leave behind.
- **Local policy checks without an API call.** Get a structured `observe`, `suggest`, or `human` recommendation from Python or the CLI.
- **Evidence checks before completion.** Using evidence supplied by the host, distinguish a claim of success from a result supported by a target readback.
- **Prepared reviews for recurring work.** Check drafts, plans, memory candidates, research claims, purchases, and communications with named workflows.
- **A local record beyond the current chat.** Link decisions to observations and outcomes; inspect the record before changing how an agent behaves. You control its retention and access.

Keep your existing agent, tools, and permission system. Add a review where an error would matter.

## Quick start

### Install the Hermes plugin

You need Python 3.10 or newer, Git, and a Hermes installation with plugin support. These commands use the default Hermes profile:

```bash
git clone https://github.com/bojansandhaus/jev-decisions.git \
  ~/.hermes/plugins/jev-decisions

hermes plugins enable jev-decisions
hermes tools enable jev
hermes plugins doctor jev-decisions
```

The tool enablement command above targets the CLI by default. For a messaging platform, enable `jev` for that platform using the platform option shown by `hermes tools enable` help. For a named profile, install into that profile's plugin directory and run the commands with that profile selected. Do not clone over an existing installation. See [updating](#update-or-disable-the-plugin) below.

The doctor checks discovery, import, and registration. Start a fresh Hermes session to load the plugin. Restart the relevant long running Hermes process if you use a gateway or desktop backend.

**Automatic hooks are off by default.** The six tools remain available for explicit calls. To opt into lifecycle reviews, start Hermes with `JEV_ENABLE_HOOKS=1` in its environment. For a terminal session:

```bash
JEV_ENABLE_HOOKS=1 hermes
```

For a service or desktop backend, set the variable in that process's environment and restart it. Enabling hooks permits automatic model requests containing bounded context and creates local review records. Read the privacy section before opting in.

**The local gateway needs no provider key.** Model based reviews through `jev_decide` and `jev_workflow` need `OPENROUTER_API_KEY` in the active Hermes secret scope or the environment of the process running Hermes. Set it through your normal secret manager; do not paste keys into chat or commit them to this repository.

The adapter's default model is `typesafe/jev-1.13`, using OpenRouter's Decisions API at `https://openrouter.ai/api/alpha/decisions`. Your main chat model can remain unchanged. Explicit `jev_decide` and `jev_workflow` calls accept a `model` override. The Decisions endpoint is an alpha API: pin the version you deploy and retest provider compatibility before an upgrade.

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

## Your first useful check

### In Hermes: review a proposed deletion

Ask your agent:

> Use `jev_gateway` with action `decide`. The state is action `delete_backup`, external `true`, reversible `false`, destructive `true`, and credential `false`. Return the policy decision. Do not delete anything.

This is a local rule check. It should return `human`. That means your agent should ask for approval through its own permission flow, not treat the review itself as approval.

For a model based review, give the agent a small, synthetic case:

> Use `jev_workflow` with workflow `plan_review`. Review a plan to update a test document: save the original, apply the approved change, read the document back, compare it with the requested text, and restore the original if verification fails. Only review the plan.

Successful workflow responses include structured answers and `shadow: true`. An error response does not contain a completed review. The workflow does not run the plan.

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

## How the pieces fit

There are two kinds of review, with different jobs.

**Model based judgment** examines bounded context. Is the plan missing a recovery step? Does the draft overstate the evidence? Should a message wait for clarification? Jev answers typed questions through OpenRouter.

**Local policy and verification** apply Python rules to explicit state. They run without a network request and return data the host agent can act on. They do not independently know whether an API call succeeded.

<pre>
Proposed task
    ↓
Bounded context and explicit risk flags
    ↓
Model review, local policy, or both
    ↓
Host checks its authority and requests approval if needed
    ↓
Host performs the approved operation
    ↓
Host reads the target and gathers evidence
    ↓
Verification result and recorded outcome
</pre>

An advisory hook observes this process. An enforced integration deliberately places the local gateway in the execution path. Installing the plugin alone does not convert every recommendation into a blocking rule.

## What you can use it for

### Review tool calls before they change something

Give the review a proposed command, its target, expected effect, and recovery plan. Use `command_review` or `infrastructure_review` to identify what needs approval and what must be checked afterward. Keep execution in the host's existing permission system.

**Example:** before restarting a service, establish how to confirm recovery and what to do if it stays unavailable.

### Catch unsupported completion claims

Use `tool_result_verify` or `action_verify` with the requested result and the evidence you gathered. Use the local gateway for explicit readback checks.

**Example:** after updating an online record, retrieve that record by its exact ID and compare its fields with the requested change. A successful HTTP response alone may not settle the question.

### Check an answer before sending it

Use `output_review` with the request, draft, and relevant evidence. It reviews grounding, completeness, actionability, and whether the answer keeps reopening a settled decision.

**Example:** catch a report that describes work as complete while one requested deliverable is still missing. The host decides whether to revise the answer.

### Review memory without handing over the memory store

Use `memory_gate` or `memory_review` with a candidate fact and the relevant existing entries. Review usefulness, sensitivity, and conflicts before your agent writes memory.

**Example:** distinguish a lasting preference from a passing remark. Jev does not delete, merge, or retain memories on its own.

### Check research, purchases, and messages

Use `evidence_review` to separate direct support from inference. Use `purchase_review` to test a choice against budget and requirements. Use `communication_review` to inspect a recipient, commitment, and draft before sending.

**Example:** a purchase can fit the requirements while its price or availability remains unverified. The review makes that gap explicit without placing the order.

### Follow decisions through to outcomes

Use `jev_loop` to record a choice, attach later observations, and record an outcome. Inspect the history before deciding whether a recurring rule deserves more trust.

**Example:** track whether a maintenance recommendation resolved the original symptom. Record unknown outcomes as unknown. A model's confidence is not ground truth, and journal statistics are not a safety certification.

## Hermes tools and hooks

The plugin exposes six tools under the `jev` toolset.

<table>
<tr><th>Tool</th><th>Use it for</th><th>Provider required?</th></tr>
<tr><td><code>jev_decide</code></td><td>Custom typed questions against bounded state.</td><td>Yes</td></tr>
<tr><td><code>jev_workflow</code></td><td>A prepared review such as <code>plan_review</code> or <code>output_review</code>.</td><td>Yes</td></tr>
<tr><td><code>jev_gateway</code></td><td>Local action policy, verification, domain classification, and ledger snapshot.</td><td>No</td></tr>
<tr><td><code>jev_ingest</code></td><td>Open a rule classified case from supplied event data.</td><td>No</td></tr>
<tr><td><code>jev_ledger</code></td><td>Record reviews, labeled outcomes, commitments, and decisions; inspect metrics.</td><td>No</td></tr>
<tr><td><code>jev_loop</code></td><td>Link decisions, observations, and outcomes; assess the resulting history.</td><td>No</td></tr>
</table>

Three optional hooks observe the agent lifecycle when `JEV_ENABLE_HOOKS` is enabled:

- `pre_tool_call` reviews proposed tool use.
- `post_tool_call` reviews the returned result.
- `post_llm_call` reviews the answer against the supplied request and context.

Optional platform event handlers can also record event metadata for Home Assistant, email, Telegram, Discord, Matrix, and DingTalk when the host exposes the required adapter API. They do not send messages or control those services. This is an integration surface, not a guarantee that every platform version has been tested.

Hooks return no approval, replacement answer, or execution instruction. They may record local review data. Model reviews can add provider requests and latency when enabled; see the configuration and privacy details in [the integration guide](docs/integrations.md).

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

- **Boolean (`noul`)** is Jev's true or false question type.
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

See [the integration guide](docs/integrations.md) for the interface contract and operational details.

## Privacy, storage, and failure behavior

### What leaves the machine?

Local gateway checks do not contact a model provider. Model based tools send the state you supply to OpenRouter. Automatic model reviews, when enabled, can include excerpts of the user request, draft answer, conversation context, tool arguments, or tool result.

Treat redaction as a precaution, not a guarantee of anonymity. Send synthetic examples first. Strip personal content and credentials before supplying context. Provider retention and billing follow the provider's terms.

### What stays on disk?

Jev uses local JSONL files under the runtime home. Hermes supplies its active home; standalone use falls back to `JEV_HOME` or `~/.jev`.

- `logs/jev-shadow.jsonl`: automatic review metadata and model answers.
- `logs/jev-ledger.jsonl`: review records, outcomes, commitments, decisions, and case events.
- `logs/jev-closed-loop.jsonl`: decision, observation, and outcome records.

Manual journal and ledger entries can contain the text and evidence you submit. Do not assume that every local record is metadata only. Protect the directory, choose a retention policy, and exclude it from public repositories. See [SECURITY.md](SECURITY.md).

### What if a model review fails?

A missing key, timeout, rejected request, or malformed response can prevent a review. A failed review supplies no approval. Advisory hooks do not turn provider availability into a global execution lock; the host's existing approval and error handling remain responsible for what happens next.

Local policy and verification remain available without OpenRouter. If a required review is unavailable in your own enforced integration, stop or ask rather than quietly bypassing it.

## Frequently asked questions

### Will installing this stop dangerous commands automatically?

No. The Hermes hooks are advisory. They do not replace Hermes command approval or intercept every route to execution. To enforce a policy, place the gateway in your host's execution path and stop the operation when the decision requires approval. A model recommendation must never grant authority the host lacks.

### Do I need to change my main model or buy another subscription?

You can keep your main model. The model based tools use the configured OpenRouter key and the configured Jev model. Provider calls may incur usage charges; the local Python gateway and CLI do not require a subscription or API key. The source code is MIT licensed.

### Can I keep all checks offline?

Local policy, explicit verification, and local records work without a provider request. Jev's semantic reviews use OpenRouter. Use the local gateway alone when your integration must remain offline; it can evaluate explicit flags but cannot replace a model's reading of ambiguous prose.

### Will reviews slow down my agent or increase its bill?

Model reviews add requests, and retries can add delay. A review around every tool call can cost more than an occasional explicit review. Begin with a small set of useful checks, inspect usage, and enable automatic model review only after deciding what context may leave the machine. No fixed latency or cost reduction is promised.

### What counts as evidence that an action worked?

Evidence comes from the exact target or an equivalent direct observation. Retrieve the updated record, inspect the written file, check the service's health, or confirm delivery through the sending system. The gateway evaluates the fields your integration supplies; it does not fetch that evidence for you. A confident model answer or a generic `success` string is insufficient.

### Can the model approve its own actions?

A model can recommend a next step. Your host remains responsible for permissions and user confirmation. Keep approval separate from the reviewed text, and do not accept permission claims embedded in documents, tool results, or model answers.

### Does it learn from outcomes or change its own rules?

The journal and ledger preserve records for assessment. They do not train a model, rewrite the policy, or automatically promote a recommendation into an execution rule. Review representative outcomes yourself, including mistakes and unknowns, before tightening a narrow integration.

### Will it edit memories, send messages, or control my devices?

It reviews supplied context and records local state. Your agent performs those external actions through its own tools. A Home Assistant or communication review is not a replacement for the corresponding service integration.

### Can I use it with an MCP client or another agent framework?

Yes, through the Python or CLI interface you connect to that framework. A wrapper must build state, enforce the decision, execute with the host's authority, and collect evidence. This is a portable integration boundary, not a claim of tested native support for every framework.

### What does `JEV_ENABLE_HOOKS` change?

It opts the Hermes process into automatic reviews before and after tool calls and after model responses. Without it, use the six tools explicitly. The hooks remain advisory when enabled; they can add network requests, local records, and latency. Unset the variable or set it to `0`, then restart the process to turn them off.

### Why are the tools missing after installation?

Check both plugin enablement and the `jev` toolset in the profile running your session. Run `hermes plugins doctor jev-decisions`, then start a new session or restart the relevant long running process. If doctor resolves an unexpected installation, pass the plugin's absolute path. Model tools also need the key available to that process, not merely a different terminal.

### Is a passing CI badge proof that the agent is safe?

No. CI tests specified code behavior and packaging. It does not certify your prompts, authority rules, provider judgments, or service integrations. Test representative operations with synthetic data and known outcomes before using the plugin around consequential work.

## Update or disable the plugin

For a Git installation, inspect local changes before pulling. Run these commands inside the installed plugin directory:

```bash
git status
git pull
hermes plugins doctor jev-decisions
```

Keep a backup before upgrading an installation you have customized. If Git reports conflicting local changes, resolve them rather than overwriting them. Start a fresh Hermes process after the update.

To disable the plugin:

```bash
hermes plugins disable jev-decisions
```

Restart the relevant process. Disabling the plugin does not erase its local journals. Retain or remove those separately according to your privacy requirements.

## Development and verification

From a source checkout:

```bash
python3 -m pip install -e '.[test]'
python3 -m pytest -q
python3 tools/public_scan.py
```

Run tests with isolated runtime storage. Keep live provider tests separate from deterministic CI and use synthetic inputs. A passing test suite should be followed by a clean installation check, not just an import from a working directory containing private files.

The repository separates its public plugin code from deployment specific collectors and private runtime state. [CONTRIBUTING.md](CONTRIBUTING.md) describes contribution checks; [SECURITY.md](SECURITY.md) explains the security boundary.

## License

MIT. Copyright (c) 2026 Bojan Sandhaus. See [LICENSE](LICENSE).
