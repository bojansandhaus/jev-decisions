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


def test_loop_handler_verifies_without_requiring_a_label(plugin):
    result = json.loads(plugin.jev_loop_handler({
        'action': 'verify_observation',
        'source': 'docker',
        'result': 'running',
    }))
    assert result['success'] is True
    assert result['verified'] is False
    assert result['next'] == 'compare_expected'


def test_loop_handler_labels_only_on_explicit_label_action(plugin):
    result = json.loads(plugin.jev_loop_handler({
        'action': 'label_outcome',
        'decision_id': 'decision-1',
        'success': True,
        'evidence': {'read_back': True},
    }))
    assert result['success'] is True
    assert result['kind'] == 'outcome_label'


def test_provider_schema_failure_is_not_retried(monkeypatch, plugin):
    import __init__ as package
    calls = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return b'{}'

    monkeypatch.setattr(package, 'urlopen', lambda *args, **kwargs: calls.append(1) or Response())
    with pytest.raises(RuntimeError, match='no valid answers map'):
        package._request({'state': {}, 'questions': {}}, 'synthetic')
    assert len(calls) == 1
