import json

from plugins.simulation.simulation_backend.application.connector_protocol_v2 import probe_context


def test_global_visibility_recovery_carries_the_expected_convergent_state():
    plan = {
        "steps": [{
            "step_id": "step-1",
            "operation_id": "vismockup.visibility.change@1",
            "payload": {"action": "all_off"},
            "side_effect_classification": "write",
            "post_condition_probe_id": "vismockup.document.snapshot@1",
        }],
    }
    context = probe_context({
        "plan_json": json.dumps(plan), "outcome_json": None,
        "plan_id": "plan-1", "plan_hash": "hash", "lease_id": "lease-1",
        "runtime_instance_id": "runtime-1", "runtime_generation": 1,
        "device_id": "device-1", "tenant_gid": "tenant-1",
    }, {"recovery_instance_id": "recovery-1", "token_hash": "token"}, last_journal_sequence=3)

    assert context["required_probes"][0]["probe_input"] == {"expected_all_visible": False}
