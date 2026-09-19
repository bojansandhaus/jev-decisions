import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    spec = importlib.util.spec_from_file_location('public_contract', ROOT / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_observation_expected_value_is_exposed_in_tool_schema():
    plugin = load_plugin()
    assert 'expected' in plugin.JEV_LOOP_SCHEMA['parameters']['properties']
    args = {'action': 'verify_observation', 'source': 'ha',
            'expected': 'on', 'result': {'state': 'off'}}
    assert json.loads(plugin.jev_loop_handler(args))['verified'] is False
    args['result'] = {'state': 'on'}
    assert json.loads(plugin.jev_loop_handler(args))['verified'] is True


def test_public_labeler_default_is_user(monkeypatch, tmp_path):
    import closed_loop
    monkeypatch.setattr(closed_loop, 'get_hermes_home', lambda: str(tmp_path))
    closed_loop.label_outcome('example', True, {'fixture': True})
    assert closed_loop.list_records()[-1]['labeler'] == 'user'


def test_reference_covers_public_actions_and_workflows():
    plugin = load_plugin()
    reference = (ROOT / 'docs/reference.md').read_text()
    for schema in (plugin.JEV_GATEWAY_SCHEMA, plugin.JEV_LEDGER_SCHEMA, plugin.JEV_LOOP_SCHEMA):
        for action in schema['parameters']['properties']['action']['enum']:
            assert f'`{action}`' in reference, action
    for workflow in plugin._WORKFLOW_QUESTIONS:
        assert f'`{workflow}`' in reference, workflow
