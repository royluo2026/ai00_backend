from plugins.simulation.simulation_backend.domain.bop_vm_binding import build_binding_draft


def _snapshot(*refs):
    return {"nodes": [{"node_key": str(index + 1), "product_ref": ref}
                      for index, ref in enumerate(refs)]}


def test_parts_use_exact_unique_product_identity_and_load_semantics():
    execution = {"operations": [
        {"operation_id": "op-load", "products": [{"product_ref": "P-100"}],
         "parameters": {"is_load_part": True, "vpps": "V-ignored"}},
        {"operation_id": "op-use", "products": [{"product_ref": "P-200"}],
         "parameters": {"is_load_part": False}},
    ]}

    draft = build_binding_draft(execution, _snapshot("P-100", "P-200"))

    assert draft["mode"] == "parts"
    assert [(item["bop_node_gid"], item["vm_node_key"], item["role"], item["disposition"])
            for item in draft["bindings"]] == [
        ("op-load", "1", "load", "auto"),
        ("op-use", "2", "operate", "auto"),
    ]


def test_vpps_only_uses_exact_unique_vpps_and_never_fuzzy_names():
    execution = {"operations": [
        {"operation_id": "op-1", "products": [], "parameters": {"vpps": "VPPS-A"}},
        {"operation_id": "op-2", "products": [], "parameters": {"vpps": "looks similar"}},
    ]}

    draft = build_binding_draft(execution, _snapshot("VPPS-A", "looks-similar"))

    assert draft["mode"] == "vpps"
    assert draft["bindings"][0]["match_basis"] == "vpps_exact"
    assert draft["bindings"][0]["confidence_milli"] == 960
    assert draft["unmatched_bop_node_gids"] == ["op-2"]


def test_no_part_information_builds_structure_only_without_guessing():
    draft = build_binding_draft(
        {"operations": [{"operation_id": "op-1", "products": [], "parameters": {}}]},
        _snapshot("P-100", "P-200"),
    )

    assert draft["mode"] == "structure_only"
    assert draft["bindings"] == []
    assert draft["unmatched_bop_node_gids"] == ["op-1"]
    assert draft["unmatched_vm_node_keys"] == ["1", "2"]


def test_duplicate_vm_identity_is_review_not_automatic():
    execution = {"operations": [{
        "operation_id": "op-1", "products": [{"product_ref": "P-100"}],
        "parameters": {"is_load_part": True},
    }]}

    draft = build_binding_draft(execution, _snapshot("P-100", "P-100"))

    assert [item["disposition"] for item in draft["bindings"]] == ["ambiguous", "ambiguous"]
    assert draft["auto_count"] == 0
    assert draft["review_count"] == 2


def test_multiple_load_claims_for_one_vm_node_are_demoted_to_conflict():
    execution = {"operations": [
        {"operation_id": "op-1", "products": [{"product_ref": "P-100"}], "parameters": {"is_load_part": True}},
        {"operation_id": "op-2", "products": [{"product_ref": "P-100"}], "parameters": {"is_load_part": True}},
    ]}

    draft = build_binding_draft(execution, _snapshot("P-100"))

    assert [item["disposition"] for item in draft["bindings"]] == ["conflict", "conflict"]
    assert all(item["conflict_code"] == "multiple_load_claims" for item in draft["bindings"])
