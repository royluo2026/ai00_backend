from .support import key, stable_capabilities


def test_async_and_local_work_always_publish_operation_recovery_contracts():
    for item in stable_capabilities():
        if item["execution_mode"] in {"cloud_async", "local"}:
            assert item["operation_policy"] == "required", key(item)
            assert item["timeout_seconds"] > 0, key(item)


def test_concurrency_contract_names_the_expected_version_payload():
    for item in stable_capabilities():
        if item["concurrency_policy"] == "expected_version":
            assert item["expected_version_payload_path"], key(item)
            root_field = item["expected_version_payload_path"].split(".", 1)[0]
            assert root_field in item["input_schema"]["properties"], key(item)


def test_failure_taxonomy_is_machine_actionable():
    for item in stable_capabilities():
        gateway_codes = set(item["gateway_errors"])
        assert {"invalid_input", "authorization_failed", "resource_scope_denied"} <= gateway_codes, key(item)
        assert len(gateway_codes) == len(item["gateway_errors"]), key(item)
