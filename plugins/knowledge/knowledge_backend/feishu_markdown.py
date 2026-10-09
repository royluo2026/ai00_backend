"""Pure, loss-aware Feishu Docx block to Markdown conversion."""
from __future__ import annotations

import re
import html
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ConversionResult:
    markdown: str
    anchors: list[dict]
    diagnostics: list[dict]
    complete: bool


def _inline(elements: list[dict], diagnostics: list[dict], block_id: str) -> str:
    chunks = []
    for element in elements:
        run = element.get("text_run")
        if run is not None:
            content = html.escape(str(run.get("content") or ""), quote=False)
            style = run.get("text_element_style") or element.get("text_element_style") or {}
            if style.get("inline_code"):
                content = f"`{content.replace('`', '\\`')}`"
            else:
                content = re.sub(r"([\\*_`\[\]])", r"\\\1", content)
                if style.get("bold"):
                    content = f"**{content}**"
                if style.get("italic"):
                    content = f"*{content}*"
                if style.get("strikethrough"):
                    content = f"~~{content}~~"
            link = (style.get("link") or {}).get("url")
            if link:
                if re.match(r"^https?://", link, re.I):
                    content = f"[{content}]({link.replace(')', '%29')})"
                else:
                    diagnostics.append({"block_id": block_id, "code": "unsafe_link", "detail": str(link)[:200]})
            chunks.append(content)
        elif element.get("mention_doc"):
            mention = element["mention_doc"]
            title = re.sub(r"([\\*_`\[\]])", r"\\\1", html.escape(str(mention.get("title") or "文档"), quote=False))
            url = str(mention.get("url") or "")
            if re.match(r"^https://[^\s)]+$", url, re.I):
                chunks.append(f"[{title}]({url})")
            else:
                chunks.append(title)
                diagnostics.append({"block_id": block_id, "code": "mention_doc_unresolved"})
        elif element.get("equation"):
            chunks.append(f"${element['equation'].get('content') or ''}$")
        else:
            diagnostics.append({"block_id": block_id, "code": "unsupported_inline"})
    return "".join(chunks)


def convert_blocks(blocks: list[dict], *, resolve_asset: Callable[[str, str], str] | None = None,
                   source_url: str = "") -> ConversionResult:
    by_id = {str(block.get("block_id")): block for block in blocks if block.get("block_id")}
    roots = [block for block in blocks if block.get("block_type") == 1]
    diagnostics: list[dict] = []
    anchors: list[dict] = []
    parts: list[str] = []
    if len(by_id) != len(blocks):
        diagnostics.append({"block_id": "", "code": "duplicate_or_missing_block_id"})
    if len(roots) != 1:
        return ConversionResult("", [], diagnostics + [{"block_id": "", "code": "document_root_missing"}], False)

    source_link = source_url if re.match(r"^https://[^\s)]+$", source_url, re.I) else ""

    def visual_reference(block_id: str, label: str) -> str:
        reference = f"飞书原文：{label}（区块 {block_id}，需人工核对）"
        return f"[{reference}]({source_link})" if source_link else reference

    def plain_cell(cell_id: str) -> str:
        cell = by_id.get(cell_id)
        if not cell or cell.get("block_type") != 32:
            diagnostics.append({"block_id": cell_id, "code": "table_cell_missing"})
            return ""
        contents = []
        for child_id in cell.get("children") or []:
            child = by_id.get(child_id)
            if not child:
                diagnostics.append({"block_id": child_id, "code": "table_cell_content_unsupported"})
                continue
            if child.get("block_type") == 27:
                diagnostics.append({"block_id": child_id, "code": "image_requires_manual_review", "detail": "表格内图片待核对"})
                contents.append(visual_reference(child_id, "表格内图片"))
                continue
            if child.get("block_type") not in {2, 3, 4, 5, 6, 7, 8, 9, 10, 11}:
                diagnostics.append({"block_id": child_id, "code": "table_cell_content_unsupported"})
                contents.append(visual_reference(child_id, "表格单元格内容"))
                continue
            key = "text" if child["block_type"] == 2 else f"heading{child['block_type'] - 2}"
            contents.append(_inline((child.get(key) or {}).get("elements") or [], diagnostics, child_id))
        return "<br>".join(contents).replace("|", "\\|").replace("\n", "<br>")

    def render(block_id: str, path: list[int], depth: int = 0, prefix: str = "") -> None:
        def emit(value: str) -> None:
            parts.append(prefix + value + "\n")

        block = by_id.get(block_id)
        if not block:
            diagnostics.append({"block_id": block_id, "code": "block_missing"})
            return
        kind = int(block.get("block_type") or 0)
        start = sum(map(len, parts))
        if 2 <= kind <= 17 and kind != 16:
            key = {2: "text", 12: "bullet", 13: "ordered", 14: "code", 15: "quote", 17: "todo"}.get(kind) or f"heading{kind - 2}"
            content = _inline((block.get(key) or {}).get("elements") or [], diagnostics, block_id)
            if 3 <= kind <= 11:
                emit(f"{'#' * (kind - 2)} {content}")
            elif kind in {12, 13, 17}:
                marker = "- " if kind == 12 else "1. " if kind == 13 else "- [x] " if (block.get("todo") or {}).get("style", {}).get("done") else "- [ ] "
                emit(f"{'  ' * depth}{marker}{content}")
            elif kind == 14:
                raw = "".join(str((e.get("text_run") or {}).get("content") or "") for e in (block.get("code") or {}).get("elements") or [])
                fence = "`" * max(3, max((len(match.group()) for match in re.finditer(r"`+", raw)), default=0) + 1)
                emit(fence)
                emit(raw.rstrip("\n"))
                emit(fence)
            elif kind == 15:
                emit(f"> {content}")
            else:
                emit(content)
            for index, child in enumerate(block.get("children") or []):
                render(child, path + [index], depth + 1 if kind in {12, 13, 17} else depth, prefix)
            if kind not in {12, 13, 17}:
                emit("")
        elif kind == 19:
            emit("> [!NOTE]")
            for index, child in enumerate(block.get("children") or []):
                render(child, path + [index], depth, prefix + "> ")
            emit("")
        elif kind == 22:
            emit("---"); emit("")
        elif kind in {23, 24, 25, 33}:
            for index, child in enumerate(block.get("children") or []):
                render(child, path + [index], depth, prefix)
        elif kind == 27:
            token = str((block.get("image") or {}).get("token") or "")
            if not token or not resolve_asset:
                diagnostics.append({"block_id": block_id, "code": "image_requires_manual_review", "detail": "图片待处理"})
                emit(visual_reference(block_id, "图片")); emit("")
            else:
                try:
                    ref = resolve_asset(token, "image")
                    emit(f"![image]({ref})"); emit("")
                except Exception as exc:
                    diagnostics.append({"block_id": block_id, "code": "image_asset_unavailable", "detail": str(exc)[:200]})
                    emit(visual_reference(block_id, "图片")); emit("")
        elif kind in {30, 43}:
            label = "电子表格" if kind == 30 else "白板"
            diagnostics.append({"block_id": block_id, "code": "embedded_visual_requires_manual_review", "detail": label})
            emit(visual_reference(block_id, label)); emit("")
        elif kind == 31:
            prop = (block.get("table") or {}).get("property") or {}
            rows, columns = int(prop.get("row_size") or 0), int(prop.get("column_size") or 0)
            cells = block.get("children") or []
            if not rows or not columns or rows * columns != len(cells) or rows > 500 or columns > 50:
                diagnostics.append({"block_id": block_id, "code": "table_structure_incomplete"})
            else:
                for row_no in range(rows):
                    values = [plain_cell(cells[row_no * columns + col]) for col in range(columns)]
                    emit("| " + " | ".join(values) + " |")
                    if row_no == 0:
                        emit("| " + " | ".join(["---"] * columns) + " |")
                emit("")
        else:
            diagnostics.append({"block_id": block_id, "code": "unsupported_block", "block_type": kind})
        anchors.append({"block_id": block_id, "path": path, "start": start, "end": sum(map(len, parts))})

    for index, block_id in enumerate(roots[0].get("children") or []):
        render(block_id, [index])
    markdown = "".join(parts).rstrip("\n") + "\n"
    for anchor in anchors:
        anchor["start"] = min(anchor["start"], len(markdown))
        anchor["end"] = min(anchor["end"], len(markdown))
    return ConversionResult(markdown, anchors, diagnostics, not diagnostics)
