<p align="center">
  <strong>README</strong> ·
  <a href="docs/reference.md"><strong>Technical reference</strong></a> ·
  <a href="docs/integrations.md">Integration guide</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="LICENSE">MIT license</a>
</p>

<div align="center">
  <h1>Jev Decisions Plugin for Hermes (and other AI Agents)</h1>
  <p><strong>Help Hermes check its plans and its work.</strong></p>
  <p>Review a risky change, catch an unsupported claim, or check what still needs doing.</p>
  <p>
    <a href="https://github.com/bojansandhaus/jev-decisions/actions/workflows/ci.yml"><img src="https://github.com/bojansandhaus/jev-decisions/actions/workflows/ci.yml/badge.svg" alt="Jev Decisions CI status"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="MIT License"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-3776AB.svg" alt="Python 3.10 or newer"></a>
  </p>
  <p>
    <a href="#install-in-hermes">Install</a> ·
    <a href="#try-it-in-a-conversation">Try it</a> ·
    <a href="#what-is-jev">About the model</a> ·
    <a href="#frequently-asked-questions">FAQ</a> ·
    <a href="docs/reference.md">Technical reference</a>
  </p>
</div>

**Jev Decisions Plugin for Hermes (and other AI Agents)** gives Hermes extra tools for reviewing a plan, checking an answer against its sources, and assessing whether a task is really finished. You can ask for a review in a normal conversation. Your usual model continues to do the work.

Suppose Hermes updates a document and tells you it is done. Did it open the saved document and check the change, or just receive a successful response from the editing tool? This plugin helps make that distinction explicit. Hermes still needs to gather the evidence.

It is useful when you trust Hermes to work independently but want closer checks around file changes, messages, research, and other tasks where a confident mistake would matter.

> [!IMPORTANT]
> Reviews are advice. Installing this plugin does not automatically stop dangerous commands or replace your approval settings. Automatic reviews are off by default; begin by asking for specific checks.

## What you can ask it to check

<table>
<tr><th>When you are using Hermes to...</th><th>Ask Jev to review...</th></tr>
<tr><td>Change a file or restart a service</td><td>Whether the plan includes permission, a way to recover, and a check afterward.</td></tr>
<tr><td>Research a question or write a report</td><td>Whether the supplied sources support the claims and whether anything important is missing.</td></tr>
<tr><td>Draft a message</td><td>Whether it is ready to send, contains sensitive information, or makes an unintended commitment.</td></tr>
<tr><td>Save something to memory</td><td>Whether the proposed memory is useful later, sensitive, or in conflict with an existing fact.</td></tr>
<tr><td>Compare purchases or choose a next step</td><td>Whether the choice fits your requirements and what information is still missing.</td></tr>
<tr><td>Follow up on a decision</td><td>What happened afterward, using a local record of observations and outcomes.</td></tr>
</table>

The plugin includes 25 prepared reviews. You do not need to learn their formats to try them: ask Hermes to use the appropriate Jev review and explain the result. See the [full review catalog](docs/reference.md#prepared-review-catalog) when you want a particular check.

## Put it to work on a real task

A useful review changes what happens next. Ask Hermes to bring back the issue, the evidence, and a concrete correction, rather than merely announce that another model agreed.

### Before a change: find the missing step

> Before changing these files, use Jev's `plan_review` on your proposed steps. Include what I authorized, how you will preserve the originals, and how you will check the saved result. Show me any gaps before you proceed.

Hermes prepares the plan and submits the relevant details. Jev assesses it. If recovery or verification is missing, Hermes can revise the plan before any file is touched. Your original permission limits still apply.

### Before a report: separate facts from assumptions

> Use `evidence_review` on this draft and the sources you actually read. Then tell me which important claims still need support. Do not invent a citation to fill a gap.

Supply the source excerpts as well as the draft. A bibliography alone does not let a reviewer compare a claim with what the source says. This is particularly useful when a polished answer mixes observed facts with plausible guesses.

### After a change: check the result, not the promise

> Read the exact record you changed. Compare it with my request, then use `action_verify` to review the result. Tell me what matched, what did not, and what you could not check.

The order matters: perform the authorized action, collect evidence, then review. Asking a model to judge a success message without reading the target adds another opinion, not proof.

### Later: find out whether the decision helped

> Use `jev_loop` to record this decision and what would count as success. When I bring back the result, attach it to the same decision. Leave the outcome unknown until we have evidence.

That gives a recurring choice a history. You can inspect whether a maintenance recommendation fixed the symptom or whether a purchasing decision met the original requirements. Keep sensitive details out of the record unless you intend to store them locally.

## Choose how much checking you want

<table>
<tr><th>Start here</th><th>What you get</th><th>What to expect</th></tr>
<tr><td><strong>One requested review</strong></td><td>A focused check discussed in your conversation.</td><td>Ask Hermes to use the named review. Model reviews require OpenRouter.</td></tr>
<tr><td><strong>Local checks only</strong></td><td>Fixed rules for approval and supplied verification evidence.</td><td>No model request. Hermes must supply accurate facts; these rules do not interpret the whole task.</td></tr>
<tr><td><strong>Automatic observation</strong></td><td>Review records around tool activity and answers.</td><td>Opt in explicitly. Additional requests, records, and delay are possible; commands are not blocked.</td></tr>
</table>

For most people, one explicit review before an important change is the best starting point. Leave routine, harmless questions alone. Add more checks only when they answer a question you actually care about.

## What is Jev?

[Jev 1.13](https://openrouter.ai/typesafe/jev-1.13) is a decision model made by **TypeSafe**. It reads the information supplied to it and answers focused questions: how likely something is to be true, which option fits, or how something scores against a set of criteria. It returns those answers with numbers that express uncertainty. It does not write chat replies or explanations.

This plugin connects those reviews to Hermes through OpenRouter. Hermes can interpret the returned answers for you; it should not present its explanation as reasoning supplied by Jev. You keep the main model you already use.

The plugin also includes simple local rules for checking whether an action needs approval and whether Hermes has supplied evidence of a completed change. Those checks work without a model request.

Read more from the sources:

- **[Jev 1.13 on OpenRouter](https://openrouter.ai/typesafe/jev-1.13):** model details, current pricing, and provider information.
- **[TypeSafe introduces Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev):** the creator's explanation of the model and why it was built.
- **[TypeSafe's guide to System One models](https://docs.typesafe.ai/concepts/system-one.md):** how these focused decisions differ from a chat model's replies, including what confidence can and cannot tell you.

This is an independent, community maintained plugin by Bojan Sandhaus. Jev is TypeSafe's model; OpenRouter provides the API used here. This repository is not an official release from either company.

## Decision history and local reports

You can keep a decision, attach later observations, label the outcome, and reopen it when new evidence changes the picture. Ask Hermes to use `jev_loop` and keep the decision ID so follow-up entries stay connected. Unknown outcomes remain unknown; the journal does not quietly count them as failures.

For a direct state comparison, ask `jev_loop` to use `verify_observation` with the expected value and an actual readback. An available device is not necessarily in the state you requested. The comparison checks the values supplied to it; Hermes must still read the correct target.

Supporting Python commands provide case lists, commitment candidates, and review summaries. They help inspect the records behind a conversation. They are not a separate graphical dashboard, and private infrastructure collectors are not included in the public package. See [tool actions](docs/reference.md#tool-actions-and-records) and [reports](docs/reference.md#reports-and-supporting-commands) for the exact interfaces.

## Install in Hermes

**Platform note:** this release uses POSIX journal locking. Linux is tested in CI. On Windows, use a Linux environment such as WSL; native Windows support is not verified and the locking module is unavailable there.

You need Git, Python 3.10 or newer, and a Hermes installation with plugin support. In a terminal, run:

```bash
git clone https://github.com/bojansandhaus/jev-decisions.git \
  ~/.hermes/plugins/jev-decisions

hermes plugins enable jev-decisions
hermes tools enable jev
hermes plugins doctor jev-decisions
```

These commands target the default Hermes profile and enable the tools for the CLI. If you use a named profile or a messaging platform, use that profile's plugin directory and tool settings. If the plugin is already installed, follow [the update instructions](#update-or-disable) instead of cloning over it.

The doctor should report successful discovery and registration of six tools and three hooks. Hooks are the optional automatic checks; registering them does not switch them on.

**For Jev model reviews, choose a provider with `JEV_PROVIDER_MODE`**: `typesafe`, `openrouter`, `typesafe_then_openrouter`, or `openrouter_then_typesafe`. The default remains `openrouter`. The plugin reads `TYPESAFE_API_KEY` for direct TypeSafe access and `OPENROUTER_API_KEY` for OpenRouter access from the active Hermes secret scope. Do not paste a key into chat or save it in this repository. The direct route uses `https://api.typesafe.ai/v1/systemone` and model `jev-1.13.0`; the OpenRouter route uses `https://openrouter.ai/api/alpha/decisions` and model `typesafe/jev-1.13`.

Start a fresh Hermes process after installation. For the desktop app or a gateway, restart the backend that runs your sessions. Opening another conversation in an unchanged backend may not load new plugin code.

## Try it in a conversation

Start with a harmless example. Paste this into Hermes:

> Use Jev's `plan_review` to review this plan: edit a test document, save it, and tell me the job is done. Identify anything missing from the plan. Only review it; do not edit any files.

Hermes should call `jev_workflow` and explain the returned assessment. Jev may flag missing recovery or verification steps, but its answer is a judgment, not a guaranteed diagnosis.

For a check that needs **no OpenRouter key**, try:

> Use `jev_gateway` to check whether deleting a backup needs human approval. Set the action to `delete_backup`, external to true, reversible to false, destructive to true, and credential to false. Do not delete anything.

The local rule should return `human`, meaning approval is required. Nothing is deleted by this check.

For everyday work, make the review part of your request:

> Draft the email, then use Jev's `communication_review` to check the recipient, sensitive details, and commitments before showing it to me. Do not send it.

> Before calling the document update complete, read the saved document and use Jev's `action_verify` to review whether the result matches what I asked for.

Hermes chooses and calls the tools. If it answers without using them, ask it to make the Jev tool call explicitly. A missing key or failed request means the review did not happen.

## Optional smart approvals

Version 0.2.1 adds selectable TypeSafe and OpenRouter routing to model reviews. Use a single provider or make either provider the primary route with the other as fallback. The companion approval only provider remains OpenRouter only in this release. It refuses ordinary chat, never executes commands, and escalates on missing or malformed evidence. Hermes's existing approval policy remains authoritative.

Installation does not select the provider, change `approvals.mode`, or enable native smart approvals. Configure it separately only after reviewing the [approval guide](docs/approvals.md). LCM, context handling, ordinary model routing, and existing tools are unchanged.

## Optional automatic reviews

Once explicit checks are useful, you can enable reviews before tool calls, after tool results, and after model responses. Start a CLI session with:

```bash
JEV_ENABLE_HOOKS=1 hermes
```

For a desktop backend or service, set `JEV_ENABLE_HOOKS=1` in that process's environment and restart it. The OpenRouter key must also be available to that process for model reviews.

Automatic reviews create local records. They do **not** insert a warning into every conversation, rewrite answers, or stop commands. Their records are useful for inspecting agent behavior; ask for an explicit review when you want a result discussed in the chat.

Enabling them can send excerpts of requests, answers, and tool activity to OpenRouter, add delay, and incur charges. Start with non-sensitive tasks. To switch them off, unset the variable or set it to `0`, then restart Hermes.

## Privacy and limits

**Reviews see what Hermes supplies.** Jev cannot check a document it has not been shown or confirm a delivery without evidence from the sending system. A high confidence score can still accompany a wrong answer.

**Model reviews leave your machine.** The relevant text goes to OpenRouter and its model provider. The local rule checks do not make those requests. Redaction reduces some exposure but cannot guarantee that private information has been removed.

**Records stay on disk until you manage them.** Automatic tool records omit raw arguments and results in favor of hashes, lengths, and review information. Manual journal entries save the text and evidence supplied to them. Protect the records and decide how long to retain them; disabling the plugin does not delete them.

**A failed review grants no permission.** If a provider request fails, Hermes must still follow its existing approval rules. Automatic reviews do not lock execution while a provider is unavailable.

The [security guide](SECURITY.md) and [integration guide](docs/integrations.md) explain these boundaries. For this early release, test unfamiliar workflows with harmless examples before using them around consequential work. CI checks the code and installation; it does not certify every model judgment or integration.

## Read the result without overreading it

A completed review should help you decide what to inspect or change. Ask Hermes for a short account:

- **What was reviewed?** The actual plan, draft, or observed result supplied to Jev.
- **What needs attention?** A missing permission, unsupported claim, incomplete result, or unresolved uncertainty.
- **What happens next?** A specific check or revision, within the authority you already granted.

Jev returns answers and probabilities, not an explanation of its reasoning. Hermes can relate those answers to the supplied material, but that explanation is Hermes's interpretation. Neither model should turn a probability into a statement that it has directly observed the world.

A review that finds no issue is still bounded by its input. If the source was stale, the target was wrong, or crucial details were omitted, agreement tells you little. Fix the input rather than repeating the same question until you get a reassuring answer.

## Frequently asked questions

### What should I try first if I only have a few minutes?

Run the harmless local backup check in [Try it in a conversation](#try-it-in-a-conversation). It confirms that Hermes can call the plugin without a provider key. Then review a short synthetic plan with `plan_review` to test the OpenRouter connection. Neither example needs permission to change your files.

### Should I ask for a review on every task?

Usually not. Start with tasks where an error would cost time, money, privacy, or trust. Check an outgoing commitment or a consequential file change before adding reviews to routine questions. Automatic observation is optional and can be noisy; more records do not necessarily mean better decisions.

### What if Jev and my main model disagree?

Ask Hermes to identify the disputed question and show the relevant evidence. Recheck the source or target when possible. If the dispute concerns your intent or permission, ask you. Neither model wins simply because it is more confident.

### How can I report a problem without exposing my data?

Reduce it to a synthetic example that still reproduces the problem. Include the plugin revision, Hermes version, tool or workflow name, expected result, and the sanitized error. Never attach your API key, complete conversation archive, or raw private journals. Follow [CONTRIBUTING.md](CONTRIBUTING.md); use the guidance in [SECURITY.md](SECURITY.md) for security concerns.

### Do I need to replace the model I use with Hermes?

No. Your usual model continues the conversation and performs the task. The plugin calls Jev separately when you request a model review or enable automatic reviews.

### Is there a subscription or extra charge?

The plugin is MIT licensed. Jev requests through OpenRouter may incur usage charges under your account. See [current model pricing](https://openrouter.ai/typesafe/jev-1.13). Local rule checks and local records need no paid provider request.

### Why use this instead of asking Hermes to double-check itself?

You can already ask Hermes to review its own work. This plugin adds prepared review questions, a separate decision model, fixed local checks, and a record you can revisit. That makes the checks more explicit and repeatable. It does not prove that two models will catch every error or that Jev will outperform your main model on every task.

### Will it prevent unsafe actions automatically?

No. Keep Hermes's existing approval settings. The plugin recommends when to ask and what to verify. Making a recommendation block an action requires additional integration; installing the plugin alone does not enforce that rule.

### Can I use it without sending anything to OpenRouter?

Yes, for the local approval and verification rules and local records. Leave automatic reviews off and avoid the model review tools. Reviews that read and judge the meaning of a plan, message, or answer require Jev through OpenRouter.

### Why did the agent say it was verified when the target was not checked?

The local verification tool relies on proof fields supplied by the caller. It requires explicit evidence that a change happened, the target was read back, and the result was supported. It cannot detect a caller inventing those facts. Ask Hermes to show what it actually read before accepting the completion claim.

### Does it learn from my decisions or change its own rules?

It records decisions and outcomes for later review. It does not train the model, rewrite its rules, or turn recommendations into automatic actions. You remain responsible for deciding which checks to trust.

### The plugin is installed, but Hermes cannot find its tools. What should I check?

Run `hermes plugins doctor jev-decisions`. Check that both the plugin and the `jev` toolset are enabled in the profile and platform you are using, then restart the relevant Hermes process. If model reviews fail, check that the OpenRouter key is available to that same process. A key set in a different terminal will not necessarily be available to the desktop backend.

### Can I use it with another agent?

Yes, if you connect its Python functions or command line tool to that agent. The portable part is the local policy, verification, and record keeping code. Native tool registration is for Hermes. This repository does not include a ready-made adapter for every agent framework. See [standalone installation and examples](docs/reference.md#install-the-standalone-python-and-cli-gateway).

## Update or disable

Inside the installed plugin directory, check for local changes before updating:

```bash
git status
git pull
hermes plugins doctor jev-decisions
```

Back up custom changes and resolve conflicts rather than overwriting them. Restart the Hermes process after an update. If you install this in a larger system, pin a tested commit and check upgrades deliberately: the provider's Decisions API is currently an alpha API.

To disable the plugin:

```bash
hermes plugins disable jev-decisions
```

Restart Hermes. Keep or remove its local journals separately, according to your privacy needs.

## For developers

The [technical reference](docs/reference.md) contains all six tools, all 25 review definitions, custom questions, Python and command line examples, and test commands. The [integration guide](docs/integrations.md) covers approval handling, evidence, provider requests, and local storage. [CONTRIBUTING.md](CONTRIBUTING.md) explains contribution checks.

The public package includes the code needed to load the plugin without private collectors or deployment files. CI tests Python 3.10, 3.11, and 3.12 and installs the package outside the checkout. Treat that as a tested starting point, then test the tasks you plan to use.

## License

MIT. Copyright (c) 2026 Bojan Sandhaus. See [LICENSE](LICENSE).
