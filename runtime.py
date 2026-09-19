"""Small runtime bridge for Hermes and standalone use.

The public project never contains credentials or private state. Hermes installs
may provide a secret scope and a profile home; standalone use falls back to the
environment and JEV_HOME.
"""
from __future__ import annotations

import os
from pathlib import Path


def get_secret(name: str) -> str | None:
    try:
        from agent.secret_scope import get_secret as hermes_get_secret
    except ImportError:
        hermes_get_secret = None
    if hermes_get_secret is not None:
        value = hermes_get_secret(name)
        if value:
            return value
    return os.environ.get(name)


def get_hermes_home() -> str:
    try:
        from hermes_constants import get_hermes_home as hermes_home
    except ImportError:
        hermes_home = None
    if hermes_home is not None:
        return str(hermes_home())
    return os.environ.get("JEV_HOME", str(Path.home() / ".jev"))
