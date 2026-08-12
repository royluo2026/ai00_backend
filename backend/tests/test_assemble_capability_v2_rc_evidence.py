from __future__ import annotations

from copy import deepcopy

import pytest

from backend.scripts.assemble_capability_v2_rc_evidence import (
    EvidenceAssemblyError,
    assemble_evidence,
)


def _runtime_evidence():
    return {
        "schema_version": 1,
        "environment_id": "rc-42",
        "run_id": "run-42",
        "git_commit": "a" * 40,
        "capabilities": {"example.read@1": {"success": "passed"}},
    }


def _database_evidence():
    return {
        "schema_version": 1,
        "environment_id": "rc-42",
        "run_id": "run-42",
        "git_commit": "a" * 40,
        "database_isolation": {
            "owner_operations": {"agent": {"migration_ledger": "passed"}},
            "cross_domain": [],
        },
    }


def test_assembly_binds_and_merges_database_evidence_without_mutating_inputs():
    runtime = _runtime_evidence()
    database = _database_evidence()
    original_runtime = deepcopy(runtime)
    original_database = deepcopy(database)

    assembled = assemble_evidence(runtime, database)

    assert assembled["database_isolation"] == database["database_isolation"]
    assert runtime == original_runtime
    assert database == original_database


@pytest.mark.parametrize("field", ["environment_id", "run_id", "git_commit"])
def test_assembly_rejects_cross_run_or_cross_environment_fragments(field):
    runtime = _runtime_evidence()
    database = _database_evidence()
    database[field] = "b" * 40 if field == "git_commit" else "other"

    with pytest.raises(EvidenceAssemblyError, match=f"binding_mismatch:{field}"):
        assemble_evidence(runtime, database)
