#!/usr/bin/env python3
"""Check the OpenRouter only route without making a provider judgment."""
import importlib.util
import os
import pathlib
import sys
import tempfile

os.environ["JEV_APPROVAL_LOG"] = str(pathlib.Path(tempfile.mkdtemp()) / "routes.jsonl")
for _candidate in (os.environ.get("HERMES_AGENT_DIR"),
                   os.path.expanduser("~/.hermes/hermes-agent")):
    if _candidate and os.path.isdir(_candidate):
        sys.path.insert(0, _candidate)
        break

_HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("jev_routes", _HERE.parent / "__init__.py")
assert spec and spec.loader
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)

base = "https://openrouter.ai/api/alpha"
endpoint, models_url, field = jev._route_for(base)
assert endpoint == "/decisions"
assert field == "data"
assert "output_modalities=decisions" in models_url
assert jev.JevClient(base_url=base, api_key="fixture")._default_model() == "~typesafe/jev-latest"

for unsupported in ("https://api.typesafe.ai/v1", "https://example.com/v1"):
    try:
        jev._route_for(unsupported)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f"unsupported route accepted: {unsupported!r}")

print("OpenRouter route verified; direct and unknown hosts rejected")
