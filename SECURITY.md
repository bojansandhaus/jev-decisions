# Security policy

## Scope

This project handles bounded state sent to an external model provider. It does not execute model recommendations and does not provide authentication for callers.

## Safe use

- Keep API keys in environment variables or a secret manager.
- Do not send credentials, private correspondence, full archives, or unnecessary personal data as state.
- Treat every model answer as untrusted data.
- Keep deterministic policy and user confirmation in front of irreversible actions.
- Read back state changing operations from the exact target.

## Reporting

Do not open a public issue for a suspected secret, credential exposure, or exploitable vulnerability. Contact the repository owner privately through GitHub security reporting if enabled, or remove the secret from active systems and rotate it before making a public report.
