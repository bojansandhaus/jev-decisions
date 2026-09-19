import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('jev_audit', ROOT / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import ledger
    import closed_loop
    monkeypatch.setattr(ledger, 'get_hermes_home', lambda: str(tmp_path))
    monkeypatch.setattr(closed_loop, 'get_hermes_home', lambda: str(tmp_path))
    monkeypatch.setattr(module, 'get_hermes_home', lambda: str(tmp_path))
    monkeypatch.setattr(module, '_secret', lambda: 'synthetic')
    monkeypatch.setattr(module, '_request', lambda *args: {'answers': {}})
    return module


def test_enabled_hooks_omit_raw_local_payload(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv('JEV_ENABLE_HOOKS', '1')
    marker = 'private_fixture_content'
    plugin._on_pre_tool_call('example', {'text': marker}, invocation_id='fixture')
    plugin._on_post_tool_call('example', {}, marker, invocation_id='fixture')
    assert marker not in '\n'.join(p.read_text() for p in tmp_path.rglob('*.jsonl'))
    import closed_loop
    outcomes = [r for r in closed_loop.list_records() if r['kind'] == 'outcome']
    assert outcomes[-1]['success'] is None


def test_post_review_receives_content_not_only_hashes(plugin, monkeypatch):
    monkeypatch.setenv('JEV_ENABLE_HOOKS', '1')
    requests = []
    monkeypatch.setattr(plugin, '_request', lambda payload, key: requests.append(payload) or {'answers': {}})
    plugin._on_post_tool_call('example', {}, 'synthetic evidence')
    assert requests[-1]['state']['result'] == 'synthetic evidence'


def test_platform_events_are_opt_in(plugin, monkeypatch, tmp_path):
    monkeypatch.delenv('JEV_ENABLE_HOOKS', raising=False)
    asyncio.run(plugin._on_platform_event({'text': 'fixture'}))
    assert not list(tmp_path.rglob('*.jsonl'))
