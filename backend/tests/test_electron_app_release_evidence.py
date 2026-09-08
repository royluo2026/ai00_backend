import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]


def test_release_manifest_closes_all_security_and_component_bindings():
    target = ROOT / 'docs/governance/electron-app-release-manifest.schema.json'
    assert target.exists(), 'Closed release manifest schema required'
    schema = json.loads(target.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    example = schema['examples'][0]
    validator = Draft202012Validator(schema)
    validator.validate(example)
    for key in schema['required']:
        incomplete = {k: v for k, v in example.items() if k != key}
        with pytest.raises(ValidationError):
            validator.validate(incomplete)
    with pytest.raises(ValidationError):
        validator.validate({**example, 'unsigned_production_bypass': True})


def test_pilot_template_never_fabricates_runtime_or_approval():
    target = ROOT / 'local-runtime/tests/pilot/electron-app-pilot-template.json'
    assert target.exists(), 'Bounded Electron pilot scenario evidence required'
    evidence = json.loads(target.read_text(encoding='utf-8'))
    assert evidence['runtime_verified'] is False
    assert evidence['human_approved'] is False
    assert evidence['technical_release_approved'] is False
    assert all(case['status'] == 'not_run' for case in evidence['scenarios'])
    assert {case['id'] for case in evidence['scenarios']} >= {
        'install', 'upgrade', 'failed_update', 'rollback', 'repair', 'uninstall',
        'single_instance', 'host_exit_with_app', 'vismockup_survival', 'pairing',
        'wake', 'normal_plan', 'duplicate_plan', 'network_loss', 'app_crash',
        'host_crash', 'com_timeout', 'reconciliation', 'vismockup_absent',
    }
