#!/usr/bin/env python3
"""JSON stdin gateway for non Hermes callers."""
from __future__ import annotations

import argparse
import json
import sys

try:
    from .gateway import decide, verify, snapshot
except ImportError:
    from gateway import decide, verify, snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["decide", "verify", "snapshot"])
    args = parser.parse_args()
    payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if not isinstance(payload, dict):
        raise SystemExit("JSON input must be an object")
    if args.action == "decide":
        result = decide(payload)
    elif args.action == "verify":
        result = verify(payload)
    else:
        result = snapshot()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
