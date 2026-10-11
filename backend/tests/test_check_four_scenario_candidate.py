from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

from backend.scripts import check_four_scenario_candidate as gate
from backend.scripts.runtime_preflight import REQUIRED_DB_URLS


def env_pair(tmp_path: Path) -> tuple[Path, Path]:
    files = []
    for environment, prefix in (("test", "test_"), ("production", "pp_")):
        path = tmp_path / f"{environment}.env"
        public_url = ("http://127.0.0.1:8080" if environment == "test"
                      else "https://workmanship-backend.chehejia.com")
        path.write_text("\n".join([
            f"AI00_DEPLOY_PROFILE={environment}", f"TABLE_PREFIX={prefix}",
            f"PUBLIC_URL={public_url}",
            *(f"{name}=mysql://{environment}_{index}:secret@db:2881/workmanship"
              for index, name in enumerate(REQUIRED_DB_URLS)),
        ]), encoding="utf-8")
        files.append(path)
    return files[0], files[1]


def candidate_paths(tmp_path: Path) -> list[Path]:
    paths = [tmp_path / name for name in (
        "test.json", "production.json", "test-browser", "test-desktop", "test-backend",
        "production-browser", "production-desktop", "production-backend")]
    for path in paths:
        if path.suffix == ".json":
            path.write_text("{}", encoding="utf-8")
        else:
            path.mkdir()
            (path / "asset.txt").write_text("original", encoding="utf-8")
    return paths


def test_pair_requires_one_configured_database_and_accepts_shared_runtime_accounts(tmp_path):
    test_env, production_env = env_pair(tmp_path)
    gate.check_environment_pair(test_env, production_env)
    source = production_env.read_text(encoding="utf-8")
    production_env.write_text(source.replace("@db:2881", "@other-db:2881"), encoding="utf-8")
    with pytest.raises(ValueError, match="one configured physical database"):
        gate.check_environment_pair(test_env, production_env)
    production_env.write_text(source.replace("production_0", "test_0", 1), encoding="utf-8")
    gate.check_environment_pair(test_env, production_env)
    for path in (test_env, production_env):
        source=path.read_text(encoding="utf-8")
        import re
        path.write_text(re.sub(r'mysql://[^:]+:', 'mysql://shared:', source),encoding="utf-8")
    gate.check_environment_pair(test_env, production_env)


def test_pair_rejects_wrong_profiles_duplicate_assignments_and_same_file(tmp_path):
    test_env, production_env = env_pair(tmp_path)
    with pytest.raises(ValueError, match="separate runtime env files"):
        gate.check_environment_pair(test_env, test_env)
    source = production_env.read_text(encoding="utf-8")
    production_env.write_text(source + "\nTABLE_PREFIX=test_\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        gate.check_environment_pair(test_env, production_env)
    production_env.write_text(source.replace("TABLE_PREFIX=pp_", "TABLE_PREFIX=test_"), encoding="utf-8")
    with pytest.raises(ValueError, match="profiles are invalid"):
        gate.check_environment_pair(test_env, production_env)


def test_pair_rejects_symlink_before_reading_config(tmp_path):
    test_env, production_env = env_pair(tmp_path)
    original = Path.lstat

    def simulated_link(path):
        return (SimpleNamespace(st_mode=stat.S_IFLNK, st_size=1)
                if path == test_env else original(path))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "lstat", simulated_link)
        with pytest.raises(ValueError, match="missing or invalid"):
            gate.check_environment_pair(test_env, production_env)
    link = tmp_path / "test-link.env"
    try:
        link.symlink_to(test_env)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available")
    with pytest.raises(ValueError, match="missing or invalid"):
        gate.check_environment_pair(link, production_env)


def test_four_scenario_gate_checks_pair_then_both_candidates_in_order(tmp_path, monkeypatch):
    test_env, production_env = env_pair(tmp_path)
    artifacts = candidate_paths(tmp_path)
    calls = []
    monkeypatch.setattr(gate, "check_candidate", lambda *args: calls.append(args))
    gate.check_four_scenario_candidate(test_env, production_env, *artifacts)
    assert calls == [
        (test_env, artifacts[0], "test", *artifacts[2:5]),
        (production_env, artifacts[1], "production", *artifacts[5:8]),
    ]
    production_env.write_text("AI00_DEPLOY_PROFILE=production\nTABLE_PREFIX=pp_", encoding="utf-8")
    with pytest.raises(ValueError, match="profiles are invalid"):
        gate.check_four_scenario_candidate(test_env, production_env, *artifacts)
    assert len(calls) == 2


def test_four_scenario_gate_stops_after_test_candidate_failure(tmp_path, monkeypatch):
    test_env, production_env = env_pair(tmp_path)
    artifacts = candidate_paths(tmp_path)
    calls = []

    def fail_test(*args):
        calls.append(args[2])
        raise ValueError("test candidate rejected")

    monkeypatch.setattr(gate, "check_candidate", fail_test)
    with pytest.raises(ValueError, match="test candidate rejected"):
        gate.check_four_scenario_candidate(test_env, production_env, *artifacts)
    assert calls == ["test"]


def test_four_scenario_gate_rejects_test_candidate_change_within_its_own_check(tmp_path, monkeypatch):
    test_env, production_env = env_pair(tmp_path)
    artifacts = candidate_paths(tmp_path)
    calls = []

    def change_during_test(*args):
        calls.append(args[2])
        if args[2] == "test":
            (artifacts[2] / "asset.txt").write_text("changed", encoding="utf-8")

    monkeypatch.setattr(gate, "check_candidate", change_during_test)
    with pytest.raises(ValueError, match="test candidate changed during four-scenario checks"):
        gate.check_four_scenario_candidate(test_env, production_env, *artifacts)
    assert calls == ["test"]


def test_four_scenario_gate_rejects_env_change_between_candidates(tmp_path, monkeypatch):
    test_env, production_env = env_pair(tmp_path)
    artifacts = candidate_paths(tmp_path)
    calls = []

    def change_production(*args):
        calls.append(args[2])
        production_env.write_text(production_env.read_text(encoding="utf-8") + "\n# changed", encoding="utf-8")

    monkeypatch.setattr(gate, "check_candidate", change_production)
    with pytest.raises(ValueError, match="changed during candidate checks"):
        gate.check_four_scenario_candidate(test_env, production_env, *artifacts)
    assert calls == ["test"]


@pytest.mark.parametrize("changed", ["manifest", "browser", "desktop", "backend"])
def test_four_scenario_gate_rejects_test_artifact_change_during_production_audit(tmp_path, monkeypatch, changed):
    test_env, production_env = env_pair(tmp_path)
    artifacts = candidate_paths(tmp_path)

    def change_after_test(*args):
        if args[2] == "production":
            target = {"manifest": artifacts[0], "browser": artifacts[2] / "asset.txt",
                      "desktop": artifacts[3] / "asset.txt", "backend": artifacts[4] / "asset.txt"}[changed]
            target.write_text("replaced", encoding="utf-8")

    monkeypatch.setattr(gate, "check_candidate", change_after_test)
    with pytest.raises(ValueError, match="test candidate changed during four-scenario checks"):
        gate.check_four_scenario_candidate(test_env, production_env, *artifacts)


@pytest.mark.parametrize("changed", ["manifest", "browser", "desktop", "backend"])
def test_four_scenario_gate_rejects_production_artifact_change_during_test_audit(tmp_path, monkeypatch, changed):
    test_env, production_env = env_pair(tmp_path)
    artifacts = candidate_paths(tmp_path)
    calls = []

    def change_during_test(*args):
        calls.append(args[2])
        if args[2] == "test":
            target = {"manifest": artifacts[1], "browser": artifacts[5] / "asset.txt",
                      "desktop": artifacts[6] / "asset.txt", "backend": artifacts[7] / "asset.txt"}[changed]
            target.write_text("replaced", encoding="utf-8")

    monkeypatch.setattr(gate, "check_candidate", change_during_test)
    with pytest.raises(ValueError, match="production candidate changed during four-scenario checks"):
        gate.check_four_scenario_candidate(test_env, production_env, *artifacts)
    assert calls == ["test"]


@pytest.mark.parametrize("changed", ["manifest", "browser", "desktop", "backend"])
def test_four_scenario_gate_rejects_production_artifact_change_during_its_audit(tmp_path, monkeypatch, changed):
    test_env, production_env = env_pair(tmp_path)
    artifacts = candidate_paths(tmp_path)

    def change_during_production(*args):
        if args[2] == "production":
            target = {"manifest": artifacts[1], "browser": artifacts[5] / "asset.txt",
                      "desktop": artifacts[6] / "asset.txt", "backend": artifacts[7] / "asset.txt"}[changed]
            target.write_text("replaced", encoding="utf-8")

    monkeypatch.setattr(gate, "check_candidate", change_during_production)
    with pytest.raises(ValueError, match="production candidate changed during four-scenario checks"):
        gate.check_four_scenario_candidate(test_env, production_env, *artifacts)


def test_four_scenario_cli_passes_exact_paths_without_running_candidates(tmp_path, monkeypatch, capsys):
    names = ("test-env", "production-env", "test-manifest", "production-manifest",
             "test-browser", "test-desktop", "test-backend", "production-browser",
             "production-desktop", "production-backend")
    values = [tmp_path / name for name in names]
    calls = []
    monkeypatch.setattr(gate, "check_four_scenario_candidate", lambda *paths: calls.append(paths))
    monkeypatch.setattr(sys, "argv", ["check_four_scenario_candidate", *(
        item for name, value in zip(names, values) for item in (f"--{name}", str(value)))])
    assert gate.main() == 0
    assert calls == [tuple(values)]
    assert "approval and rollout remain separate" in capsys.readouterr().out
