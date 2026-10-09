"""Historical Knowledge image assets remain readable without Feishu media access."""
import hashlib
from unittest.mock import patch

from plugins.knowledge.knowledge_backend.source_assets import asset_data_url


def test_historical_source_asset_reads_only_immutable_ois_object():
    data = b"\x89PNG\r\n\x1a\nimage"
    asset = {"object_key": "knowledge/test/assets/kna_1.png", "content_sha256": hashlib.sha256(data).hexdigest(),
             "byte_size": len(data), "media_type": "image/png"}
    with patch("plugins.knowledge.knowledge_backend.source_assets.get_immutable", return_value=data) as read:
        result = asset_data_url(asset)
    read.assert_called_once_with(asset["object_key"], asset["content_sha256"])
    assert result.startswith("data:image/png;base64,")
