from plugins.simulation.simulation_backend.application.environment_verification import compare_runtime_readback


EXPECTED = {"documents": [{"content_sha256": "sha256:" + "a" * 64}], "hierarchies": [{"name": "ALT", "placement_count": 2}]}


def test_readback_requires_exact_documents_hierarchies_and_successful_scene_probes():
    actual = {"documents": [{"content_sha256": "sha256:" + "a" * 64}], "hierarchies": [{"name": "ALT", "placement_count": 2}]}
    report = compare_runtime_readback(EXPECTED, actual, [{"operation": "hide", "matched": True}, {"operation": "select", "matched": True}])
    assert report.state == "verified"


def test_readback_failure_and_unknown_outcome_are_not_collapsed():
    failed = compare_runtime_readback(EXPECTED, {"documents": [], "hierarchies": []}, [])
    unknown = compare_runtime_readback(EXPECTED, {}, [{"operation": "hide", "outcome_unknown": True}])
    assert failed.state == "failed" and failed.mismatches
    assert unknown.state == "outcome_unknown"
