# Optional smart approvals

Jev Decisions 0.2.0 includes an approval only companion provider and an advisory `approval_review` workflow. Both are opt in. The provider sees only commands already sent to Hermes's approval gate. It is not a sandbox, command detector, or executor.

## OpenRouter requirement

Model reviews and smart approval review require an OpenRouter API key in the active Hermes profile. Store it through the Hermes secret manager or the profile environment as `OPENROUTER_API_KEY`. Never put a key in `config.yaml`, a command argument, a journal, or this repository.

The typed endpoint is `https://openrouter.ai/api/alpha/decisions` and the default model is `typesafe/jev-1.13`. A provider outage, missing key, timeout, malformed response, invalid number, unknown enum, or incomplete answer is an unavailable review and must escalate. It never silently approves.

## Advisory workflow

Ask Hermes to run `jev_workflow` with `workflow: approval_review` and bounded state containing the command, its description, and trusted operator policy separately. The result includes the Jev answers, a verdict, and the deterministic rule applied. The workflow is shadow only. It cannot authorize or execute a command, and caller supplied policy is not authenticated operator authorization.

## Native provider

The companion manifest is in `integrations/approval-provider`. It registers an approval only model provider through Hermes provider discovery. It must not be selected for the main model, ordinary auxiliary tasks, or chat. Activation is a separate setup action and installation does not change `approvals.mode`, `auxiliary.approval`, the main model, or `context.engine`.

When you explicitly activate it, use provider `jev-decisions-approval` with an OpenRouter base URL such as `https://openrouter.ai/api/alpha` and model `~typesafe/jev-latest`. This release rejects direct TypeSafe endpoints and unknown hosts.

Keep the existing Hermes approval settings in force. Before selecting the provider, run the registration and routing tests with a mocked transport, then exercise a harmless flagged command in a fresh Hermes process. Test disabled and manual modes as well as an unavailable key. Do not enable it unattended until representative labeled outcomes show acceptable false approvals and unnecessary escalations.

## Privacy and attribution

Commands are bounded and redacted before provider egress where the integration can do so. Local records contain metadata and hashes rather than raw command text. Review payloads still leave the machine for OpenRouter, so use synthetic cases when testing.

The companion provider is adapted from [anpicasso/hermes-jev-approvals](https://github.com/anpicasso/hermes-jev-approvals), authored by anpicasso. See `THIRD_PARTY_NOTICES.md` for the applicable MIT notice. The surrounding Jev Decisions plugin remains Copyright (c) 2026 Bojan Sandhaus under MIT.
