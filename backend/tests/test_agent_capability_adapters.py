from plugins.agent.agent_backend.ai_assistant.tool_handlers import capability_tools


def test_bop_structure_adapter_preserves_evidence(monkeypatch):
    calls = []

    def fake_invoke(capability_id, payload, user_gid, auth_mode):
        calls.append((capability_id, payload, user_gid, auth_mode))
        return {
            "data": {
                "nodes": [{"kind": "operation", "name": "装配", "vpps": "OP10"}],
                "operations": [],
            },
            "evidence": [{"kind": "craft.bop.execution_structure", "reference": "craft://bop/v1"}],
        }

    monkeypatch.setattr(capability_tools, "_invoke", fake_invoke)
    result = capability_tools.dispatch_bop_structure(
        {"version_gid": "v1"}, user_gid="u1", auth_mode="web"
    )

    assert calls == [("craft.bop.execution_structure.get", {"version_gid": "v1"}, "u1", "web")]
    assert result["source"] == "capability"
    assert result["evidence"][0]["reference"] == "craft://bop/v1"
    assert "装配" in result["text"]


def test_ontology_adapter_resolves_then_reads_pinned_schema(monkeypatch):
    calls = []

    def fake_invoke(capability_id, payload, user_gid, auth_mode):
        calls.append((capability_id, payload, user_gid, auth_mode))
        if capability_id == "ontology.concept.resolve":
            return {
                "data": {
                    "status": "resolved",
                    "release_gid": "r1",
                    "concept": {"stable_gid": "operation", "kind": "concept", "label_zh": "工序"},
                },
                "evidence": [{"reference": "ois://ontology/r1"}],
            }
        return {
            "data": {"concept": {"stable_gid": "operation", "properties": ["duration"]}},
            "evidence": [{"reference": "ois://ontology/r1"}],
        }

    monkeypatch.setattr(capability_tools, "_invoke", fake_invoke)
    result = capability_tools.dispatch_ontology(
        {"node_type": "operation"}, user_gid="u1", auth_mode="feishu"
    )

    assert calls[0][0] == "ontology.concept.resolve"
    assert calls[1][0] == "ontology.concept.get"
    assert calls[1][1] == {
        "stable_gid": "operation",
        "kind": "concept",
        "release_gid": "r1",
        "view": "schema",
    }
    assert result["source"] == "capability"
    assert len(result["evidence"]) == 2
