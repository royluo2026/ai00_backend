import importlib

import pytest


@pytest.mark.parametrize("module_name", [
    "backend.ontology.proposals",
    "plugins.ontology.ontology_backend.proposals",
])
@pytest.mark.parametrize("field,value", [
    ("name", "modified type"),
    ("name", "123process"),
    ("name", "critical-process"),
    ("name", "关键工艺"),
    ("mapped_column", "critical process"),
    ("name", True),
    ("mapped_column", 123),
])
def test_property_changes_reject_unsafe_identifiers(module_name, field, value) -> None:
    proposals = importlib.import_module(module_name)
    with pytest.raises(ValueError, match=field):
        proposals.normalize_changes([{
            "operation": "property.add",
            "stable_gid": "property.test",
            "value": {"name": "valid_name", field: value},
        }])


@pytest.mark.parametrize("module_name", [
    "backend.ontology.proposals",
    "plugins.ontology.ontology_backend.proposals",
])
def test_property_changes_accept_safe_or_empty_mapped_column(module_name) -> None:
    proposals = importlib.import_module(module_name)
    changes = proposals.normalize_changes([
        {"operation": "property.add", "stable_gid": "property.safe", "value": {"name": "critical_process", "mapped_column": "critical_process"}},
        {"operation": "property.change", "stable_gid": "property.other", "value": {"mapped_column": ""}},
    ])
    assert len(changes) == 2
