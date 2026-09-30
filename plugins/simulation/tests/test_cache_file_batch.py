import pytest

from plugins.simulation.simulation_backend.data.cloud_model_cache_repository import CacheError


FILES = [
    {"node_key": f"node-{i}", "dataset_uid": f"dataset-{i}", "file_uid": f"file-{i}"}
    for i in range(3)
]
IDENTITY = {"batch_id": "a" * 32, "generation": "b" * 32,
            "snapshot_hash": "sha256:" + "c" * 64, "schema_version": 1}


def test_legacy_receipt_hash_only_changes_the_size_bound():
    from copy import deepcopy
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_file_contracts import FILE_CONTRACT
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import canonical_hash
    from plugins.simulation.simulation_backend.data.cache_file_receipt_validation import LEGACY_FILE_CONTRACT_HASH
    legacy=deepcopy(FILE_CONTRACT)
    legacy['output']['properties']['byte_length']['maximum']=100*1024*1024
    assert canonical_hash(legacy)==LEGACY_FILE_CONTRACT_HASH


@pytest.mark.parametrize('legacy', [False,True])
@pytest.mark.parametrize('size', [32,264498976,512*1024*1024,512*1024*1024+1])
def test_singleton_preflight_uses_512_mib_limit(size,legacy):
    from plugins.simulation.simulation_backend.data.cache_file_receipt_validation import validate_cached_file_batch_result
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import build_file_batch_steps
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_file_contracts import FILE_OUTPUT
    from jsonschema import validate,ValidationError
    member={**IDENTITY,'node_key':'node','item_revision_uid':'rev',
            'file_ref':{'dataset_uid':'dataset','file_uid':'file','file_name':'part.jt','relation_type':'IMAN_Rendering'},'expected_content_hash':None}
    plan={'plan_id':'op','plan_hash':'sha256:'+'e'*64,'capability_id':'simulation.model_cache.file.fetch.batch.request',
          'steps':build_file_batch_steps(IDENTITY,{'object_uid':'root'},[member])}
    if legacy:
        from plugins.simulation.simulation_backend.data.cache_file_receipt_validation import LEGACY_FILE_CONTRACT_HASH
        plan['steps'][1]['contract_hash']=LEGACY_FILE_CONTRACT_HASH
    exceeded=size>(100 if legacy else 512)*1024*1024
    file={'identity':IDENTITY,'node_key':'node','item_revision_uid':'rev','file_ref':member['file_ref'],
          'artifact_ref':{'artifact_id':'artifact-1','media_type':'model/jt','sha256':'d'*64,'byte_size':size,'version':1},
          'content_hash':'sha256:'+'d'*64,'byte_length':size,'acquired_at':'2026-09-29T00:00:00Z','captured_bytes_verified':False}
    error='cache_file_batch_size_exceeded' if exceeded else None
    preflight={'identity':IDENTITY,'files':[{'step_id':'step-00002','node_key':'node','item_revision_uid':'rev','file_ref':member['file_ref'],'file_size':size}],
               'total_byte_length':size,'error_code':error}
    steps=[{'step_id':'step-00001','status':'failed_without_effect' if exceeded else 'succeeded','result':preflight}]
    if not exceeded:steps.append({'step_id':'step-00002','status':'succeeded','result':file})
    outcome={'plan_id':'op','plan_hash':plan['plan_hash'],'overall_status':'failed_without_effect' if exceeded else 'succeeded','steps':steps}
    result=validate_cached_file_batch_result(IDENTITY,[member],'op',plan,{'status':'failed' if exceeded else 'completed','outcome':outcome})
    assert result['preflight']['total_byte_length']==size
    assert result['files'][0]['file']==(None if exceeded else file)
    if size>512*1024*1024:
        with pytest.raises(ValidationError):validate(file,FILE_OUTPUT)
    else:validate(file,FILE_OUTPUT)


def test_batch_request_is_bounded_and_rejects_duplicate_members():
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_files import normalize_batch_files

    assert normalize_batch_files(FILES) == FILES
    with pytest.raises(CacheError, match="cache_file_batch_size_invalid"):
        normalize_batch_files([])
    with pytest.raises(CacheError, match="cache_file_batch_size_invalid"):
        normalize_batch_files(FILES * 3)
    with pytest.raises(CacheError, match="cache_file_batch_duplicate_member"):
        normalize_batch_files([FILES[0], dict(FILES[0])])


def test_batch_plan_maps_each_exact_member_to_one_fetch_step_after_preflight():
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import build_file_batch_steps
    from plugins.simulation.simulation_backend.capabilities.cloud_model_cache_file_contracts import FILE_INPUT
    from jsonschema import validate

    members = [
        {**IDENTITY, "node_key": item["node_key"], "item_revision_uid": f"rev-{i}",
         "file_ref": {"dataset_uid": item["dataset_uid"], "file_uid": item["file_uid"],
                      "file_name": f"part-{i}.jt", "relation_type": "IMAN_Rendering"},
         "expected_content_hash": None}
        for i, item in enumerate(FILES)
    ]
    selector = {"endpoint_id": "tc-production", "object_uid": "root", "item_revision_uid": "rev",
                "bom_view_uid": "", "revision_rule": "Latest Working", "configuration_date": "2026-09-29T00:00:00Z"}
    steps = build_file_batch_steps(IDENTITY, selector, members)
    for step in steps[1:]:
        validate(step["payload"], FILE_INPUT)
        assert step["payload"]["source_selector"] == selector

    assert len(steps) == 4
    assert steps[0]["operation_id"] == "teamcenter.model_files.size.preflight@1"
    assert [step["step_id"] for step in steps[1:]] == ["step-00002", "step-00003", "step-00004"]
    assert [step["payload"]["file_ref"]["file_uid"] for step in steps[1:]] == ["file-0", "file-1", "file-2"]
    assert all(step["depends_on"] == ["step-00001"] for step in steps[1:])
    assert [item["step_id"] for item in steps[0]["payload"]["files"]] == [
        "step-00002", "step-00003", "step-00004"
    ]


def test_batch_result_validates_preflight_and_preserves_per_file_partial_outcomes():
    from plugins.simulation.simulation_backend.data.cache_file_receipt_validation import validate_cached_file_batch_result
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import build_file_batch_steps

    selected = [
        {**IDENTITY, "node_key": item["node_key"], "item_revision_uid": f"rev-{i}",
         "file_ref": {"dataset_uid": item["dataset_uid"], "file_uid": item["file_uid"],
                      "file_name": f"part-{i}.jt", "relation_type": "IMAN_Rendering"},
         "expected_content_hash": None}
        for i, item in enumerate(FILES[:2])
    ]
    members = [{**item, "step_id": f"step-{i + 2:05d}"} for i, item in enumerate(selected)]
    preflight = {"identity": IDENTITY, "files": [
        {"step_id": item["step_id"], "node_key": item["node_key"],
         "item_revision_uid": item["item_revision_uid"], "file_ref": item["file_ref"], "file_size": 100}
        for item in members
    ], "total_byte_length": 200, "error_code": None}
    fetched = {
        "identity": IDENTITY, "node_key": members[0]["node_key"],
        "item_revision_uid": members[0]["item_revision_uid"], "file_ref": members[0]["file_ref"],
        "artifact_ref": {"artifact_id": "artifact-1", "media_type": "model/jt", "sha256": "d" * 64,
                         "byte_size": 100, "version": 1},
        "content_hash": "sha256:" + "d" * 64, "byte_length": 100,
        "acquired_at": "2026-09-28T00:00:00Z", "captured_bytes_verified": False,
    }
    plan = {"plan_id":"batch-op","plan_hash":"sha256:"+"e"*64,
            "capability_id": "simulation.model_cache.file.fetch.batch.request",
            "steps": build_file_batch_steps(IDENTITY, {"object_uid": "root"}, selected)}
    outcome = {"plan_id":"batch-op","plan_hash":plan["plan_hash"],"overall_status":"failed_without_effect","steps": [
        {"step_id": "step-00001", "status": "succeeded", "result": preflight},
        {"step_id": members[0]["step_id"], "status": "succeeded", "result": fetched},
        {"step_id": members[1]["step_id"], "status": "failed_without_effect", "error_code": "file_not_found"},
    ]}

    result = validate_cached_file_batch_result(IDENTITY, members, "batch-op", plan,
        {"status": "failed", "outcome": outcome})
    assert [item["status"] for item in result["files"]] == ["succeeded", "failed_without_effect"]
    assert result["files"][0]["file"]["content_hash"] == fetched["content_hash"]

    original_selector = plan["steps"][1]["payload"].pop("source_selector")
    with pytest.raises(CacheError, match="cache_file_operation_mismatch"):
        validate_cached_file_batch_result(IDENTITY, members, "batch-op", plan,
            {"status": "failed", "outcome": outcome})
    plan["steps"][1]["payload"]["source_selector"] = {"object_uid": "other-source"}
    with pytest.raises(CacheError, match="cache_file_operation_mismatch"):
        validate_cached_file_batch_result(IDENTITY, members, "batch-op", plan,
            {"status": "failed", "outcome": outcome})
    plan["steps"][1]["payload"]["source_selector"] = original_selector

    outcome["steps"][0]["result"]["total_byte_length"] = 201
    with pytest.raises(CacheError, match="cache_file_result_invalid"):
        validate_cached_file_batch_result(IDENTITY, members, "batch-op", plan,
            {"status": "failed", "outcome": outcome})


def test_preflight_size_rejection_returns_total_and_never_claims_member_attempts():
    from plugins.simulation.simulation_backend.data.cache_file_receipt_validation import validate_cached_file_batch_result
    from plugins.simulation.simulation_backend.capabilities.connector_runtime import build_file_batch_steps

    selected = [
        {**IDENTITY, "node_key": item["node_key"], "item_revision_uid": f"rev-{i}",
         "file_ref": {"dataset_uid": item["dataset_uid"], "file_uid": item["file_uid"],
                      "file_name": f"part-{i}.jt", "relation_type": "IMAN_Rendering"},
         "expected_content_hash": None}
        for i, item in enumerate(FILES[:2])
    ]
    members = [{**item, "step_id": f"step-{i + 2:05d}"} for i, item in enumerate(selected)]
    total = 110 * 1024 * 1024
    preflight = {"identity": IDENTITY, "files": [
        {"step_id": item["step_id"], "node_key": item["node_key"],
         "item_revision_uid": item["item_revision_uid"], "file_ref": item["file_ref"],
         "file_size": total // 2}
        for item in members
    ], "total_byte_length": total, "error_code": "cache_file_batch_size_exceeded"}
    plan = {"plan_id":"batch-op","plan_hash":"sha256:"+"e"*64,
            "capability_id": "simulation.model_cache.file.fetch.batch.request",
            "steps": build_file_batch_steps(IDENTITY, {"object_uid": "root"}, selected)}
    outcome = {"plan_id":"batch-op","plan_hash":plan["plan_hash"],"overall_status":"failed_without_effect",
               "steps": [{"step_id": "step-00001", "status": "failed_without_effect",
                           "result": preflight, "error_code": "cache_file_batch_size_exceeded"}]}

    result = validate_cached_file_batch_result(IDENTITY, members, "batch-op", plan,
        {"status": "failed", "outcome": outcome})
    assert result["preflight"] == {"status": "failed_without_effect",
                                   "error_code": "cache_file_batch_size_exceeded",
                                   "total_byte_length": total}
    assert all(item["status"] == "failed_without_effect" and item["not_attempted"]
               and item["file"] is None for item in result["files"])
    # Older malformed plans remain readable as no-effect failures for recovery.
    for step in plan["steps"][1:]:
        step["payload"].pop("source_selector")
    assert validate_cached_file_batch_result(IDENTITY, members, "batch-op", plan,
        {"status": "failed", "outcome": outcome}) == result
