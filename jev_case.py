#!/usr/bin/env python3
"""Open, close, or list cross system Jev cases as JSON."""
from __future__ import annotations

import argparse
import json
import sys

try:
    from .fabric import close_case, open_case, queue
except ImportError:
    from fabric import close_case, open_case, queue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["open", "close", "list"])
    parser.add_argument("--case-id")
    parser.add_argument("--domain")
    parser.add_argument("--status", default="resolved")
    args = parser.parse_args()
    payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if args.action == "open":
        result = {"case_id": open_case(args.domain or "unknown", payload)}
    elif args.action == "close":
        if not args.case_id:
            raise SystemExit("--case-id is required")
        result = {"entry_id": close_case(args.case_id, args.status, payload)}
    else:
        result = {"cases": queue(status=payload.get("status"), domain=payload.get("domain"))}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
