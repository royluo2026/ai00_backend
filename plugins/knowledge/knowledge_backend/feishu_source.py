"""Complete Feishu Docx reads; incomplete pagination is never importable."""
from __future__ import annotations

from urllib.parse import urlparse

from backend.services.feishu_service import feishu_service
from .feishu_catalog import parse_document_url


def read_all_blocks(fetch_page, *, max_pages: int = 200, max_blocks: int = 20000) -> list[dict]:
    blocks: list[dict] = []
    token = None
    seen = set()
    for _ in range(max_pages):
        if token in seen:
            raise ValueError("incomplete Feishu document pagination: repeated page token")
        seen.add(token)
        page = fetch_page(token)
        items = page.get("items")
        if not isinstance(items, list):
            raise ValueError("incomplete Feishu document pagination: missing blocks")
        blocks.extend(items)
        if len(blocks) > max_blocks:
            raise ValueError("Feishu document block limit exceeded")
        if not page.get("has_more"):
            return blocks
        token = page.get("page_token")
        if not token:
            raise ValueError("incomplete Feishu document pagination: missing next page")
    raise ValueError("incomplete Feishu document pagination: page limit exceeded")


def read_document_blocks(document_url: str) -> tuple[str, list[dict]]:
    token = parse_document_url(document_url)
    kind = urlparse(document_url).path.split("/")[1]
    if kind == "wiki":
        node = feishu_service.resolve_wiki_node(token)
        if node.get("obj_type") != "docx" or not node.get("obj_token"):
            raise ValueError("Wiki node is not a Docx document")
        token = str(node["obj_token"])
    blocks = read_all_blocks(lambda page: feishu_service.get_doc_blocks_page(token, page))
    return token, blocks
