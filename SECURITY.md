# Security

Jev Decisions reviews actions and checks evidence. It does not execute model recommendations and it does not provide authentication for callers.

## Safe use

- Keep API keys and passwords in a secret manager or environment variable.
- Send the provider only the smallest amount of information needed for the question.
- Do not send private correspondence, full archives, credentials, or unrelated personal data.
- Treat every model answer as a recommendation, never as permission.
- Keep human approval in front of destructive or difficult to reverse actions.
- Read the exact target back after every state changing operation.
- Networked observer hooks are disabled unless `JEV_ENABLE_HOOKS` is explicitly enabled.
- Hook records omit submitted tool arguments and result text, but manual journal tools persist the text they receive.

## Report a security problem

Do not publish a suspected secret or security weakness in a public issue. Contact the repository owner privately through GitHub security reporting if enabled. Rotate exposed credentials before discussing the incident publicly.
