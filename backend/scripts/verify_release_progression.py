"""Read-only artifact/version progression gate against a prior release manifest."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from backend.release_version import ARTIFACT_FIELDS, MANIFEST_FIELDS, SHA256_PATTERN, _read_regular_text

SEMVER = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z')


def parse_version(value):
    match = SEMVER.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError(f'invalid version: {value!r}')
    pre = match[4].split('.') if match[4] else []
    if any(item.isdigit() and len(item) > 1 and item.startswith('0') for item in pre):
        raise ValueError('invalid numeric prerelease identifier')
    return tuple(int(match[index]) for index in (1, 2, 3)), pre


def compare_versions(left, right):
    a, ap = parse_version(left)
    b, bp = parse_version(right)
    if a != b:
        return 1 if a > b else -1
    if not ap or not bp:
        return (bool(bp) > bool(ap)) - (bool(bp) < bool(ap))
    for x, y in zip(ap, bp):
        if x == y:
            continue
        if x.isdigit() and y.isdigit():
            return 1 if int(x) > int(y) else -1
        if x.isdigit() != y.isdigit():
            return -1 if x.isdigit() else 1
        return 1 if x > y else -1
    return (len(ap) > len(bp)) - (len(ap) < len(bp))


def validate_manifest(manifest):
    if (not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS
            or type(manifest['schemaVersion']) is not int or manifest['schemaVersion'] != 1
            or manifest['environment'] not in ('test', 'production')
            or not isinstance(manifest['frontendVersions'], dict)
            or set(manifest['frontendVersions']) != {'browser', 'desktop'}
            or not isinstance(manifest['artifactSha256'], dict)
            or set(manifest['artifactSha256']) != ARTIFACT_FIELDS):
        raise ValueError('invalid release manifest schema')
    for value in (manifest['programVersion'], manifest['backendVersion'], *manifest['frontendVersions'].values()):
        _, prerelease = parse_version(value)
        if manifest['environment'] == 'production' and prerelease:
            raise ValueError('production versions must be stable')
    if any(not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value)
           for value in manifest['artifactSha256'].values()):
        raise ValueError('invalid artifact hash')


def verify_progression(candidate, previous):
    validate_manifest(candidate)
    validate_manifest(previous)
    if candidate['environment'] != previous['environment']:
        raise ValueError('baseline environment mismatch')
    changed = False
    for component in ('browser', 'desktop', 'backend'):
        old = previous['backendVersion'] if component == 'backend' else previous['frontendVersions'][component]
        new = candidate['backendVersion'] if component == 'backend' else candidate['frontendVersions'][component]
        comparison = compare_versions(new, old)
        different = candidate['artifactSha256'][component] != previous['artifactSha256'][component]
        if comparison < 0 or (different and comparison <= 0):
            raise ValueError(f'{component} version must increase: {old} -> {new}')
        changed |= different or comparison != 0
    overall = compare_versions(candidate['programVersion'], previous['programVersion'])
    if overall < 0 or (changed and overall <= 0):
        raise ValueError(f'program version must increase: {previous["programVersion"]} -> {candidate["programVersion"]}')


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate manifest key')
        result[key] = value
    return result


def read_manifest(path, role):
    source = _read_regular_text(path, 65536)
    if source is None:
        raise ValueError(f'{role} manifest missing or not a bounded regular file: {path}')
    return json.loads(source, object_pairs_hook=unique_keys)


def check_progression(candidate_path: Path, baseline_path: Path):
    if candidate_path.resolve() == baseline_path.resolve():
        raise ValueError('baseline must be a separate prior manifest')
    candidate = read_manifest(candidate_path, 'candidate')
    verify_progression(candidate, read_manifest(baseline_path, 'baseline'))
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--previous-manifest', type=Path, required=True)
    parser.add_argument('--browser-artifact', type=Path, required=True)
    parser.add_argument('--desktop-artifact', type=Path, required=True)
    parser.add_argument('--backend-artifact', type=Path, required=True)
    parser.add_argument('--layout', choices=('release', 'demo'), default='release')
    args = parser.parse_args()
    manifest = check_progression(args.manifest, args.previous_manifest)
    from backend.scripts.verify_release_artifacts import artifact_sha256, verify_release_artifacts
    if args.layout == 'release':
        verify_release_artifacts(args.manifest, manifest['environment'], args.browser_artifact,
                                 args.desktop_artifact, args.backend_artifact)
    else:
        # DEMO retains its legacy expanded layout; it cannot claim a production release.
        if manifest['environment'] != 'test':
            raise ValueError('demo packaging requires test environment')
        package = json.loads((args.desktop_artifact / 'app/package.json').read_text(encoding='utf-8'))
        if package['version'] != manifest['frontendVersions']['desktop']:
            raise ValueError('desktop installer/package version mismatch')
        browser_html = (args.browser_artifact / 'web/index.html').read_text(encoding='utf-8')
        version = re.search(r'<meta\s+name="app-version"\s+content="([^"]+)"', browser_html)
        if not version or version[1] != manifest['frontendVersions']['browser']:
            raise ValueError('browser page version mismatch')
        desktop_html = (args.desktop_artifact / 'app/dist-test-governance/web/index.html').read_text(encoding='utf-8')
        version = re.search(r'<meta\s+name="app-version"\s+content="([^"]+)"', desktop_html)
        if not version or version[1] != manifest['frontendVersions']['desktop']:
            raise ValueError('desktop page version mismatch')
        if (args.backend_artifact / 'backend/VERSION').read_text(encoding='utf-8').strip() != manifest['backendVersion']:
            raise ValueError('backend version mismatch')
        for name, artifact in (('browser', args.browser_artifact), ('desktop', args.desktop_artifact), ('backend', args.backend_artifact)):
            if artifact_sha256(artifact) != manifest['artifactSha256'][name]:
                raise ValueError(f'{name} artifact hash mismatch')
    print('release versions increased where artifacts changed; artifact binding verified; baseline unchanged')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
