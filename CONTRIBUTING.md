# Contributing

Jev Decisions is a safety layer for Hermes and other AI agents. Keep changes small, clear, testable, and safe to run outside Hermes.

Before opening a pull request:

```bash
python3 -m pytest -q
python3 -m compileall -q .
python3 tools/public_scan.py
```

Do not commit keys, passwords, private conversations, local logs, session files, caches, or private test data. Do not add code that lets a model recommendation execute an action without the host agent's authority checks.

Use commit prefixes such as `feat:`, `fix:`, `docs:`, `test:`, and `chore:`. Explain the user problem your change solves and include a generic example when the behavior changes.
