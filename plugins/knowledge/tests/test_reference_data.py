from __future__ import annotations

from plugins.knowledge.knowledge_backend.application.reference_data import ReferenceDataService


class Repository:
    def __init__(self):
        self.published = None

    def publish(self, dataset_gid, expected_version, schema, rows, actor_gid, tenant_gid):
        self.published = {
            "dataset_gid": dataset_gid, "version_gid": "krv-2", "version_no": expected_version + 1,
            "schema": schema, "rows": tuple(rows), "immutable": True,
        }
        return self.published

    def lookup(self, dataset_gid, version_gid, keys, tenant_gid):
        assert version_gid == "krv-2"
        return [row for row in self.published["rows"] if row["key"] in keys]


def test_reference_dataset_publish_is_immutable_and_lookup_is_version_bound():
    repository = Repository()
    service = ReferenceDataService(repository)
    version = service.publish(
        dataset_gid="labor-rate", expected_version=1,
        schema={"rate": "number"}, rows=[{"key": "CN", "rate": 1.2}, {"key": "DE", "rate": 2.4}],
        actor_gid="u1", tenant_gid="t1",
    )

    assert version["immutable"] is True
    assert service.lookup(dataset_gid="labor-rate", version_gid="krv-2", keys=["DE"], tenant_gid="t1") == [{"key": "DE", "rate": 2.4}]

