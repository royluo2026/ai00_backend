from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.simulation.simulation_backend.capabilities.vm_diffs import VmDiffProvider
from plugins.simulation.simulation_backend.domain.vm_identity import VmObservation


def observation(gid, revision):
    return VmObservation(occurrence_gid=gid, source_instance_id=f"s-{gid}", session_gid="1", kind="part",
        model_number=f"P-{gid}", bom_line=f"L-{gid}", revision=revision,
        catia_occurrence_name=f"n-{gid}", normalized_transform=("0",))


class Repository:
    def __init__(self):
        self.snapshots = {"1": {"snapshot_gid": "11", "workspace_gid": "9", "observations": [observation("7", "A")]},
                          "2": {"snapshot_gid": "12", "workspace_gid": "9", "observations": [observation("7", "B")]}}
        self.report = None

    def load_checkpoint_snapshot(self, checkpoint_gid, **scope): return self.snapshots.get(checkpoint_gid)
    def persist_report(self, **values):
        if self.report is None:
            self.report = {"report_gid": "100", "workspace_gid": values["workspace_gid"],
                "before_snapshot_gid": values["before_snapshot_gid"], "after_snapshot_gid": values["after_snapshot_gid"],
                "algorithm_version": values["algorithm_version"], "report_kind": values["report_kind"],
                "status": "completed", "summary": values["diff"].summary, "row_version": 1,
                "created_at": "2026-09-10T00:00:00Z", "archived_at": None}
            self.items = list(values["diff"].items)
        return self.report
    def get_report(self, report_gid, **scope): return self.report if self.report and report_gid == "100" else None
    def search_items(self, report_gid, **values):
        return {"items": [{"sequence": index + 1, **item.__dict__} for index, item in enumerate(self.items)], "next_cursor": None}


def context(): return CapabilityContext(user_gid="1", team_gid="2")


def test_generate_is_idempotent_and_returns_atomic_summary():
    target = VmDiffProvider(Repository())
    payload = {"before_checkpoint_gid": "1", "after_checkpoint_gid": "2", "report_kind": "manual",
               "algorithm_version": "vm-diff-v1", "idempotency_key": "once"}
    first = target.generate(payload, context()).data
    second = target.generate(payload, context()).data
    assert first == second
    assert first["summary"] == {"revision_upgraded": 1}


def test_get_and_item_search_return_only_repository_visible_report():
    target = VmDiffProvider(Repository())
    target.generate({"before_checkpoint_gid": "1", "after_checkpoint_gid": "2", "report_kind": "manual",
                     "algorithm_version": "vm-diff-v1", "idempotency_key": "once"}, context())
    assert target.get({"report_gid": "100"}, context()).data["status"] == "completed"
    page = target.search_items({"report_gid": "100", "page_size": 200}, context()).data
    assert page["items"][0]["change_type"] == "revision_upgraded"
