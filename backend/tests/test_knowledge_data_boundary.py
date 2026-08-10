from __future__ import annotations

import pytest

from backend.knowledge.data.connection import _params
from backend.knowledge.ids import new_knowledge_id


def test_knowledge_database_requires_its_own_explicit_url(monkeypatch):
    monkeypatch.delenv("AI00_KNOWLEDGE_DB_URL", raising=False)
    monkeypatch.setenv("AI00_DB_URL", "mysql://base:secret@base/base")

    with pytest.raises(RuntimeError, match="Base DB credentials are not a fallback"):
        _params()


def test_knowledge_database_url_is_parsed_without_base_configuration(monkeypatch):
    monkeypatch.setenv(
        "AI00_KNOWLEDGE_DB_URL", "mysql://knowledge_user:p%40ss@knowledge-db:3307/knowledge"
    )

    assert _params() == {
        "host": "knowledge-db",
        "port": 3307,
        "user": "knowledge_user",
        "password": "p@ss",
        "database": "knowledge",
    }


@pytest.mark.parametrize("kind,prefix", [
    ("space", "kns_"), ("document", "knd_"), ("revision", "knr_"),
    ("proposal", "knp_"), ("outbox", "kno_"), ("entry", "kne_"),
])
def test_knowledge_identifiers_are_domain_owned_and_typed(kind: str, prefix: str):
    assert new_knowledge_id(kind).startswith(prefix)


def test_knowledge_capabilities_depend_on_the_storage_port_not_base_ois_directly():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    files = [
        root / "backend/knowledge/revision_store.py",
        root / "backend/capabilities/review_next.py",
        root / "backend/capabilities/outbox_retry_next.py",
    ]
    violations = [path.name for path in files if "backend.core.ois_storage" in path.read_text(encoding="utf-8")]
    assert violations == []
