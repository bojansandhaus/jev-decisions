# Contributing

Keep changes small, typed, testable, and provider neutral where possible.

1. Run `python3 -m pytest -q`.
2. Run `python3 -m compileall -q .`.
3. Run `python3 tools/public_scan.py`.
4. Do not commit `.env`, logs, session files, caches, credentials, or private fixtures.
5. Keep Jev advisory. Do not add code that executes a model recommendation.

Use conventional commit prefixes such as `feat:`, `fix:`, `docs:`, `test:`, and `chore:`.
