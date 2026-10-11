import json

import pytest

from backend.release_version import read_system_version


def source_fixture(tmp_path):
    version = tmp_path / 'VERSION'
    version.write_text('0.1.0-dev')
    manifest = tmp_path / 'program-version.json'
    manifest.write_text(json.dumps({
        'programVersion': '1.0.7', 'backendVersion': '0.1.0-dev',
        'frontendVersions': {'browser': '1.0.7', 'desktop': '1.0.7'},
    }))
    return tmp_path / 'release-manifest.json', version, manifest


def test_development_combination_has_an_explicit_program_version(tmp_path):
    result = read_system_version(*source_fixture(tmp_path), runtime_environment='')
    assert result['programVersion'] == '1.0.7'
    assert result['versionSource'] == 'development'
    assert result['backendVersion'] == '0.1.0-dev'


@pytest.mark.parametrize('environment', ['test', 'production'])
def test_release_environment_cannot_fall_back_to_development_version(tmp_path, environment):
    result = read_system_version(*source_fixture(tmp_path), runtime_environment=environment)
    assert result['programVersion'] is None


def test_development_binding_must_match_backend(tmp_path):
    paths = source_fixture(tmp_path)
    paths[1].write_text('0.2.0-dev')
    assert read_system_version(*paths, runtime_environment='')['programVersion'] is None


def test_release_manifest_takes_precedence_over_development_version(tmp_path):
    paths = source_fixture(tmp_path)
    paths[0].write_text(json.dumps({
        'schemaVersion': 1, 'environment': 'test', 'programVersion': '2.0.0',
        'backendVersion': '0.1.0-dev', 'frontendVersions': {'browser': '1.1.0', 'desktop': '1.2.0'},
        'artifactSha256': {name: 'a' * 64 for name in ('browser', 'desktop', 'backend')},
    }))
    result = read_system_version(*paths, runtime_environment='test')
    assert result['programVersion'] == '2.0.0'
    assert result['versionSource'] == 'release'
