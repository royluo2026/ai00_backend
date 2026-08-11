from .support import key, stable_capabilities


def test_every_stable_capability_has_v2_authorization_and_bounded_resources():
    for item in stable_capabilities():
        assert ".v2:" in item["authorization_policy"], key(item)
        assert not item["authorization_policy"].startswith("legacy:"), key(item)
        for selector in item["resource_selectors"]:
            assert selector["resource_type"], key(item)
            root_field = selector["payload_path"].split(".", 1)[0]
            assert root_field in item["input_schema"]["properties"], key(item)


def test_mutations_require_gateway_confirmation_and_idempotency():
    for item in stable_capabilities():
        if item["side_effect_level"] == "read":
            assert item["confirmation_policy"] == "none", key(item)
            continue
        assert item["idempotency_policy"] == "required", key(item)
        if item["confirmation_policy"] == "none":
            assert item["id"].startswith("plugin.storage."), key(item)
            assert item["automation_level"] == "A1", key(item)
            assert {selector["resource_type"] for selector in item["resource_selectors"]} == {"plugin-storage-key"}, key(item)
        else:
            assert item["confirmation_policy"] in {"user", "admin"}, key(item)


def test_agent_and_mcp_never_receive_unbounded_secret_outputs():
    forbidden = {"secret", "token", "password", "credential", "private_key"}
    for item in stable_capabilities():
        if not (item["exposure"]["agent"] or item["exposure"]["mcp"]):
            continue
        serialized = str(item["agent_output_schema"] or item["output_schema"]).lower()
        for word in forbidden:
            assert f"'{word}'" not in serialized and f'"{word}"' not in serialized, key(item)
