import copy
import json

import pytest


def manifest():
    return {
        'schemaVersion': 1, 'environment': 'test', 'programVersion': '1.0.7',
        'frontendVersions': {'browser': '1.0.3', 'desktop': '1.0.3'},
        'backendVersion': '0.1.0-dev',
        'artifactSha256': {name: 'a' * 64 for name in ('browser', 'desktop', 'backend')},
    }


@pytest.mark.parametrize('component', ['browser', 'desktop', 'backend'])
def test_changed_artifact_requires_component_bump(component):
    from backend.scripts.verify_release_progression import verify_progression
    previous = manifest()
    candidate = copy.deepcopy(previous)
    candidate['programVersion'] = '1.0.8'
    candidate['artifactSha256'][component] = 'b' * 64
    with pytest.raises(ValueError, match=component):
        verify_progression(candidate, previous)


def test_changed_component_requires_overall_bump():
    from backend.scripts.verify_release_progression import verify_progression
    previous = manifest()
    candidate = copy.deepcopy(previous)
    candidate['artifactSha256']['browser'] = 'b' * 64
    candidate['frontendVersions']['browser'] = '1.0.4'
    with pytest.raises(ValueError, match='program'):
        verify_progression(candidate, previous)
    candidate['programVersion'] = '1.0.8'
    verify_progression(candidate, previous)


def test_identical_retry_passes_but_downgrade_does_not():
    from backend.scripts.verify_release_progression import verify_progression
    previous = manifest()
    verify_progression(copy.deepcopy(previous), previous)
    candidate = copy.deepcopy(previous)
    candidate['frontendVersions']['desktop'] = '1.0.2'
    with pytest.raises(ValueError, match='desktop'):
        verify_progression(candidate, previous)
    candidate = copy.deepcopy(previous)
    candidate['programVersion'] = '1.0.6'
    with pytest.raises(ValueError, match='program'):
        verify_progression(candidate, previous)


@pytest.mark.parametrize('old,new', [('0.1.0-dev', '0.1.0'), ('1.0.0-rc.9', '1.0.0-rc.10')])
def test_prerelease_progression_uses_semver_order(old, new):
    from backend.scripts.verify_release_progression import verify_progression
    previous = manifest()
    previous['backendVersion'] = old
    candidate = copy.deepcopy(previous)
    candidate.update(backendVersion=new, programVersion='1.0.8')
    candidate['artifactSha256']['backend'] = 'b' * 64
    verify_progression(candidate, previous)
    with pytest.raises(ValueError):
        verify_progression(previous, candidate)


def test_baseline_environment_and_strict_schema_are_required():
    from backend.scripts.verify_release_progression import verify_progression
    previous = manifest()
    for modification in ({'environment': 'production'}, {'schemaVersion': True}, {'extra': 'field'}):
        candidate = dict(previous, **modification)
        with pytest.raises(ValueError):
            verify_progression(candidate, previous)


def test_missing_or_duplicate_baseline_is_rejected_without_writes(tmp_path):
    from backend.scripts.verify_release_progression import check_progression
    candidate = tmp_path / 'candidate.json'
    original = json.dumps(manifest())
    candidate.write_text(original)
    with pytest.raises(ValueError, match='baseline'):
        check_progression(candidate, tmp_path / 'missing.json')
    baseline = tmp_path / 'baseline.json'
    baseline.write_text('{"schemaVersion":1,"schemaVersion":1}')
    with pytest.raises(ValueError):
        check_progression(candidate, baseline)
    assert candidate.read_text() == original
