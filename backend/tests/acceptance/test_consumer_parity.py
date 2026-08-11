from .support import document, key, stable_capabilities


def _tool_keys(relative):
    view = document(relative)
    return view["catalog_release"], {
        f'{item["id"]}@{item["major_version"]}' for item in view["tools"]
    }


def test_agent_and_mcp_views_are_exact_release_bound_projections():
    catalog = document("docs/capabilities/catalog.v2.json")
    visible = [item for item in catalog["capabilities"] if item["lifecycle_status"] != "retired"]

    for relative, consumer in (
        ("docs/capabilities/agent-tools.v2.json", "agent"),
        ("docs/capabilities/mcp-tools.v2.json", "mcp"),
    ):
        release, actual = _tool_keys(relative)
        expected = {key(item) for item in visible if item["exposure"][consumer]}
        assert release == catalog["release_id"]
        assert actual == expected


def test_openapi_uses_the_only_public_capability_url_for_every_descriptor():
    catalog = document("docs/capabilities/catalog.v2.json")
    paths = document("docs/capabilities/openapi-fragment.v2.json")["paths"]

    assert set(paths) == {
        f'/api/v1/capabilities/{item["id"]}:invoke'
        for item in catalog["capabilities"]
    }
    assert not any(path.startswith("/api/v2/capabilities") for path in paths)


def test_every_stable_consumer_contract_is_strict_and_schema_pinned():
    for item in stable_capabilities():
        assert item["schema_precision"] == "typed", key(item)
        assert item["input_schema"]["type"] == "object", key(item)
        assert item["input_schema"]["additionalProperties"] is False, key(item)
        assert item["schema_hash"].startswith("sha256:"), key(item)
        assert item["catalog_release"], key(item)
