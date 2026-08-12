from __future__ import annotations

from pathlib import Path

import pytest

from plugins.ontology.ontology_backend.infrastructure.connection import _params


def test_ontology_database_never_falls_back_to_shared_credentials(monkeypatch):
    monkeypatch.delenv("AI00_ONTOLOGY_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "mysql://base:secret@db/base")
    with pytest.raises(RuntimeError, match="AI00_ONTOLOGY_DB_URL"):
        _params()


def test_ontology_migration_owns_the_complete_reviewed_table_inventory():
    migration = (
        Path(__file__).parents[3]
        / "backend"
        / "db"
        / "migrations"
        / "domains"
        / "ontology"
        / "0001_ontology.sql"
    ).read_text(encoding="utf-8")

    expected_tables = {
        "workmanship_ontology_schema_migrations",
        "workmanship_base_ontology_releases",
        "workmanship_base_ontology_release_objects",
        "workmanship_base_ontology_change_proposals",
        "workmanship_base_ontology_proposal_revisions",
        "workmanship_base_ontology_proposal_reviews",
        "workmanship_base_ontology_active_refs",
        "workmanship_onto_classes",
        "workmanship_onto_properties",
        "workmanship_onto_relations",
        "workmanship_onto_axioms",
    }
    for table in expected_tables:
        assert table in migration

    assert "workmanship_bop_" not in migration
    assert "workmanship_proj_" not in migration
    assert "workmanship_know_" not in migration
