#!/usr/bin/env python3
"""Print a privacy preserving Jev cockpit snapshot."""
from __future__ import annotations

import json
import sys

try:
    from .cockpit import commitment_candidates, snapshot
except ImportError:
    from cockpit import commitment_candidates, snapshot

payload = sys.stdin.read()
if payload.strip():
    print(json.dumps({"commitments": commitment_candidates(payload), "snapshot": snapshot()}, sort_keys=True))
else:
    print(json.dumps(snapshot(), sort_keys=True))
