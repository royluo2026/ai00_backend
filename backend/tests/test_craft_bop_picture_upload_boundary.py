from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_picture_upload import apply_bop_picture_upload


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/entries.py")


def test_picture_upload_route_uses_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.picture.upload"') == 1
    assert "def _legacy_upload_bop_pic" in source


def test_picture_upload_validates_mime_before_io() -> None:
    with pytest.raises(ValueError, match="only image MIME types are allowed"):
        apply_bop_picture_upload({"filename": "x.txt", "mime": "text/plain", "data_b64": ""}, object())


def test_picture_upload_validates_base64_before_io() -> None:
    with pytest.raises(ValueError, match="invalid base64 data"):
        apply_bop_picture_upload({"filename": "x.png", "mime": "image/png", "data_b64": "!"}, object())
