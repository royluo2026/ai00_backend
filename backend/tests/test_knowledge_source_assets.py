"""Copied Feishu images get immutable tenant-scoped references."""
import hashlib
from unittest.mock import patch

from plugins.knowledge.knowledge_backend.source_assets import asset_data_url, store_source_image


def test_source_image_never_uses_a_temporary_feishu_url():
    data = b"\x89PNG\r\n\x1a\nimage"
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args): pass
        def fetchone(self): return None
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    with patch("plugins.knowledge.knowledge_backend.source_assets.feishu_service.download_doc_media", return_value=(data, "image/png")), \
         patch("plugins.knowledge.knowledge_backend.source_assets.get_knowledge_conn", return_value=Connection()), \
         patch("plugins.knowledge.knowledge_backend.source_assets.new_knowledge_id", return_value="kna_1"), \
         patch("plugins.knowledge.knowledge_backend.source_assets.put_immutable", side_effect=lambda key, payload, _media: {"object_key": key, "sha256": hashlib.sha256(payload).hexdigest()}):
        asset = store_source_image(tenant_gid="team_1", source_gid="knf_1", snapshot_gid="knsnp_1", feishu_token="image123")
    assert asset["markdown_ref"] == "knowledge-asset:kna_1"
    assert "team_1/sources/knf_1/snapshots/knsnp_1/assets" in asset["object_key"]
    with patch("plugins.knowledge.knowledge_backend.source_assets.get_immutable", return_value=data):
        assert asset_data_url(asset).startswith("data:image/png;base64,")


def test_unchanged_feishu_image_reuses_its_asset_gid_across_pulls():
    data = b"\x89PNG\r\n\x1a\nimage"
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args): pass
        def fetchone(self): return {"gid": "kna_stable", "object_key": "old-key", "byte_size": len(data), "media_type": "image/png"}
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    with patch("plugins.knowledge.knowledge_backend.source_assets.feishu_service.download_doc_media", return_value=(data, "image/png")), \
         patch("plugins.knowledge.knowledge_backend.source_assets.get_knowledge_conn", return_value=Connection()), \
         patch("plugins.knowledge.knowledge_backend.source_assets.put_immutable") as put:
        asset = store_source_image(tenant_gid="team_1", source_gid="knf_1", snapshot_gid="knsnp_2", feishu_token="image123")
    assert asset["markdown_ref"] == "knowledge-asset:kna_stable"
    assert asset["new"] is False
    put.assert_not_called()
