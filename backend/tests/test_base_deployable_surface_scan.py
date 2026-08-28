from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT.parent / "workmanship-web-capability-governance"


def _git(repo: Path, *args: str, text: bool = True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    ).stdout


def _commit_fixture(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "frontend"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "immutable-evidence@example.test")
    _git(repo, "config", "user.name", "Immutable Evidence Test")
    for relative, source in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo


def _expected_git_files(repo: Path, revision: str) -> list[dict[str, str]]:
    raw = _git(
        repo,
        "ls-tree",
        "-r",
        "--full-tree",
        revision,
        "--",
        "dist-production/packages",
        "dist-production/web",
        "packages/core/electron",
    )
    entries = []
    for line in raw.splitlines():
        metadata, path = line.split("\t", 1)
        _mode, kind, blob_oid = metadata.split()
        if kind != "blob" or Path(path).suffix.lower() not in {".cjs", ".html", ".js", ".mjs"}:
            continue
        entries.append((path, blob_oid))
    batch = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input="".join(f"{oid}\n" for _path, oid in entries).encode("ascii"),
        check=True,
        capture_output=True,
    ).stdout
    expected = []
    offset = 0
    for path, blob_oid in entries:
        header_end = batch.index(b"\n", offset)
        oid, kind, raw_size = batch[offset:header_end].decode("ascii").split()
        assert (oid, kind) == (blob_oid, "blob")
        size = int(raw_size)
        start = header_end + 1
        payload = batch[start:start + size]
        offset = start + size + 1
        expected.append({"path": path, "blob_oid": blob_oid, "sha256": hashlib.sha256(payload).hexdigest()})
    return sorted(expected, key=lambda item: item["path"])


def test_deployable_surface_report_covers_production_web_and_electron_without_retired_bypasses():
    from backend.scripts.check_base_deployable_surfaces import build_report

    report = build_report(FRONTEND)

    expected_revision = subprocess.run(
        ["git", "-C", str(FRONTEND), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert report["frontend_revision"] == expected_revision
    assert report["roots"] == [
        "dist-production/packages",
        "dist-production/web",
        "packages/core/electron",
    ]
    assert report["scan_mode"] == "commit"
    assert report["extensions"] == [".cjs", ".html", ".js", ".mjs"]
    assert report["exclusions"] == []
    assert report["findings"] == []
    expected = _expected_git_files(FRONTEND, expected_revision)
    assert report["files"] == expected
    assert report["scanned_files"] == len(expected)
    assert sum(report["root_file_counts"].values()) == len(expected)
    unsigned = {key: value for key, value in report.items() if key != "content_sha256"}
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert report["content_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()


def test_commit_scan_ignores_untracked_and_dirty_worktree_bytes(tmp_path: Path) -> None:
    from backend.scripts.check_base_deployable_surfaces import build_report

    repo = _commit_fixture(tmp_path, {
        "dist-production/packages/plugin.html": "<main>governed</main>\n",
        "dist-production/web/app.js": "window.ok = true;\n",
        "packages/core/electron/main.js": "const safe = true;\n",
    })
    before = build_report(repo)
    (repo / "dist-production/web/untracked.js").write_text(
        "localStorage.setItem(this._lsKey(), 'bypass');\n", encoding="utf-8"
    )
    (repo / "dist-production/web/app.js").write_text(
        "localStorage.getItem(this._lsKey());\n", encoding="utf-8"
    )

    assert build_report(repo) == before


def test_worktree_scan_refuses_dirty_tracked_deployable_roots(tmp_path: Path) -> None:
    from backend.scripts.check_base_deployable_surfaces import build_report

    repo = _commit_fixture(tmp_path, {
        "dist-production/packages/plugin.html": "<main>governed</main>\n",
        "dist-production/web/app.js": "window.ok = true;\n",
        "packages/core/electron/main.js": "const safe = true;\n",
    })
    (repo / "dist-production/web/app.js").write_text("window.dirty = true;\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dirty deployable worktree"):
        build_report(repo, mode="worktree")


@pytest.mark.parametrize(
    ("relative", "source", "code"),
    [
        (
            "dist-production/web/components/view_manager.js",
            "const vmFilters = []; localStorage.getItem(this._lsKey());\n",
            "silent_saved_view_local_authority",
        ),
        (
            "dist-production/web/components/view_manager.js",
            "localStorage.setItem('vm_views_base', '{}');\n",
            "silent_saved_view_local_authority",
        ),
        (
            "dist-production/web/components/tree_list_shell.js",
            "const key = 'tls_views_task'; localStorage.setItem(key, '[]');\n",
            "silent_saved_view_local_authority",
        ),
        (
            "dist-production/packages/craft-plugin/web/custom_shell.js",
            "const key = 'tls_def_task'; localStorage.setItem(key, '{}');\n",
            "silent_saved_view_local_authority",
        ),
        (
            "dist-production/web/arbitrary/preferences.js",
            "const key = 'tls_cfg_task'; localStorage.setItem(key, JSON.stringify({ vmFilters: [], vmSorts: [] }));\n",
            "silent_saved_view_local_authority",
        ),
        (
            "dist-production/packages/craft-plugin/web/named_views.js",
            "const namedViewStorageKey = 'craft_named_views'; localStorage.setItem(namedViewStorageKey, JSON.stringify([{ name: 'Open', config: { filters: [] } }]));\n",
            "silent_saved_view_local_authority",
        ),
        (
            "packages/core/electron/main.js",
            "ipcMain.handle('plugin:install-url', installFromUrl);\n",
            "retired_electron_url_install",
        ),
        (
            "packages/core/electron/main.js",
            "ipcMain.handle('plugin:uninstall-user', uninstallUserPlugin);\n",
            "retired_electron_destructive_uninstall",
        ),
    ],
)
def test_commit_scan_detects_exact_blocker_signatures(
    tmp_path: Path, relative: str, source: str, code: str
) -> None:
    from backend.scripts.check_base_deployable_surfaces import build_report

    files = {
        "dist-production/packages/plugin.html": "<main>governed</main>\n",
        "dist-production/web/app.js": "window.ok = true;\n",
        "packages/core/electron/main.js": "const safe = true;\n",
    }
    files[relative] = source
    report = build_report(_commit_fixture(tmp_path, files))

    assert code in {finding["code"] for finding in report["findings"]}


def test_tls_cfg_ephemeral_ui_preferences_do_not_trigger_saved_view_authority(
    tmp_path: Path,
) -> None:
    from backend.scripts.check_base_deployable_surfaces import build_report

    repo = _commit_fixture(tmp_path, {
        "dist-production/packages/plugin.html": "<main>governed</main>\n",
        "dist-production/web/preferences.js": (
            "const key = 'tls_cfg_task'; "
            "localStorage.setItem(key, JSON.stringify({ density: 'compact' }));\n"
        ),
        "packages/core/electron/main.js": "const safe = true;\n",
    })

    assert build_report(repo)["findings"] == []


def test_generic_ls_key_layout_cache_does_not_trigger_saved_view_authority(
    tmp_path: Path,
) -> None:
    from backend.scripts.check_base_deployable_surfaces import build_report

    repo = _commit_fixture(tmp_path, {
        "dist-production/packages/plugin.html": "<main>governed</main>\n",
        "dist-production/web/layout.js": (
            "const linePositions = {}; const layoutVersion = 5; "
            "localStorage.setItem(this._lsKey(), JSON.stringify({ linePositions, layoutVersion }));\n"
        ),
        "packages/core/electron/main.js": "const safe = true;\n",
    })

    assert build_report(repo)["findings"] == []
