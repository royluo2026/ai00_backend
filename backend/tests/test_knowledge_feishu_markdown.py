"""Complete structural conversion of Feishu Docx blocks before import."""
import pytest

from plugins.knowledge.knowledge_backend.feishu_markdown import convert_blocks
from plugins.knowledge.knowledge_backend.feishu_source import read_all_blocks
from plugins.knowledge.knowledge_backend.feishu_source import read_document_blocks
from unittest.mock import patch


def _text(block_id, kind, value, children=None):
    return {"block_id": block_id, "block_type": kind, "children": children or [],
            {2: "text", 3: "heading1", 12: "bullet", 13: "ordered"}.get(kind, "text"): {
                "elements": [{"text_run": {"content": value}}],
            }}


def test_converter_keeps_hierarchy_table_order_and_block_anchors():
    blocks = [
        {"block_id": "root", "block_type": 1, "children": ["h", "li", "table"]},
        _text("h", 3, "BOP 定义"),
        _text("li", 12, "主项", ["nested"]),
        _text("nested", 12, "子项"),
        {"block_id": "table", "block_type": 31, "children": ["c11", "c12", "c21", "c22"], "table": {"property": {"row_size": 2, "column_size": 2}}},
        *({"block_id": f"c{r}{c}", "block_type": 32, "children": [f"t{r}{c}"]} for r in (1, 2) for c in (1, 2)),
        *(_text(f"t{r}{c}", 2, f"R{r}C{c}") for r in (1, 2) for c in (1, 2)),
    ]
    result = convert_blocks(blocks)
    assert result.complete is True
    assert "# BOP 定义" in result.markdown
    assert "- 主项\n  - 子项" in result.markdown
    assert "| R1C1 | R1C2 |" in result.markdown
    assert "| R2C1 | R2C2 |" in result.markdown
    assert any(anchor["block_id"] == "nested" and anchor["path"] == [1, 0] for anchor in result.anchors)


def test_unsupported_block_or_image_without_asset_is_incomplete():
    blocks = [{"block_id": "root", "block_type": 1, "children": ["image", "unknown"]},
              {"block_id": "image", "block_type": 27, "image": {"token": "img123"}},
              {"block_id": "unknown", "block_type": 999}]
    result = convert_blocks(blocks)
    assert result.complete is False
    assert {issue["block_id"] for issue in result.diagnostics} == {"image", "unknown"}


def test_long_text_is_not_truncated():
    body = "A" * 8500
    result = convert_blocks([{"block_id": "root", "block_type": 1, "children": ["t"]}, _text("t", 2, body)])
    assert body in result.markdown


def test_rich_text_and_image_asset_use_safe_references():
    blocks = [{"block_id": "root", "block_type": 1, "children": ["rich", "image"]},
              {"block_id": "rich", "block_type": 2, "text": {"elements": [
                  {"text_run": {"content": "BOP", "text_element_style": {"bold": True, "link": {"url": "https://example.feishu.cn/docx/abc123"}}}},
              ]}},
              {"block_id": "image", "block_type": 27, "image": {"token": "image123"}}]
    result = convert_blocks(blocks, resolve_asset=lambda token, kind: f"knowledge-asset:{token}-{kind}")
    assert result.complete is True
    assert "[**BOP**](https://example.feishu.cn/docx/abc123)" in result.markdown
    assert "![image](knowledge-asset:image123-image)" in result.markdown


def test_incomplete_table_reports_exact_block():
    result = convert_blocks([{"block_id": "root", "block_type": 1, "children": ["table"]},
                             {"block_id": "table", "block_type": 31, "children": [], "table": {"property": {"row_size": 2, "column_size": 2}}}])
    assert result.complete is False
    assert result.diagnostics[0]["block_id"] == "table"


def test_feishu_text_that_looks_like_html_is_escaped():
    result = convert_blocks([{"block_id": "root", "block_type": 1, "children": ["t"]},
                             _text("t", 2, "<script>alert(1)</script>")])
    assert "<script>" not in result.markdown
    assert "&lt;script&gt;" in result.markdown


def test_block_pagination_requires_every_page():
    pages = iter([
        {"items": [{"block_id": "root", "block_type": 1}], "has_more": True, "page_token": "next"},
        {"items": [{"block_id": "t", "block_type": 2}], "has_more": False},
    ])
    assert len(read_all_blocks(lambda _token: next(pages))) == 2
    with pytest.raises(ValueError, match="incomplete"):
        read_all_blocks(lambda _token: {"items": [], "has_more": True})


def test_wiki_node_resolves_to_docx_before_block_read():
    with patch("plugins.knowledge.knowledge_backend.feishu_source.feishu_service.resolve_wiki_node", return_value={"obj_type": "docx", "obj_token": "doc123"}) as resolve, \
         patch("plugins.knowledge.knowledge_backend.feishu_source.feishu_service.get_doc_blocks_page", return_value={"items": [{"block_id": "root", "block_type": 1}], "has_more": False}) as page:
        token, blocks = read_document_blocks("https://example.feishu.cn/wiki/wiki123")
    assert token == "doc123" and len(blocks) == 1
    resolve.assert_called_once_with("wiki123")
    page.assert_called_once_with("doc123", None)
