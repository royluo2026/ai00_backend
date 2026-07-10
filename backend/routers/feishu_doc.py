"""
backend/routers/feishu_doc.py
──────────────────────────────
飞书文档集成 —— 读取内容 + 写入单元格
路由前缀：/api/feishu/doc
"""
from __future__ import annotations

import re
from fastapi import APIRouter, Depends, Body
from backend.routers.deps import get_current_user
from backend.services.feishu_service import FeishuService

router = APIRouter(prefix="/api/feishu/doc", tags=["feishu_doc"])
_svc = FeishuService()

_DOC_TOKEN_RE = re.compile(
    r"feishu\.cn/(?:docx|docs|wiki)/([A-Za-z0-9_-]+)"
)


def _extract_token(url: str) -> str | None:
    m = _DOC_TOKEN_RE.search(url)
    return m.group(1) if m else None


@router.post("/read")
def read_doc(
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    """
    读取飞书文档纯文本内容。优先使用当前用户自己的 feishu token（用户有阅读权限即可），
    若用户 token 不可用则降级到机器人 tenant token（需机器人有权限）。
    body: { "doc_url": "https://xxx.feishu.cn/docx/xxx" }
    返回: { "content": "...", "doc_token": "...", "char_count": N }
    """
    doc_url = body.get("doc_url", "")
    token = _extract_token(doc_url)
    if not token:
        return {"error": "无法从 URL 中提取文档 token，请确认是飞书文档链接"}
    try:
        # 优先用用户自己的飞书 token
        from backend.services import user_service as _us
        user_feishu_token = _us.get_feishu_token(current_user["gid"])
        if user_feishu_token:
            content = _svc.get_doc_raw_content_as_user(token, user_feishu_token)
        else:
            # 降级：机器人 tenant token
            content = _svc.get_doc_raw_content(token)
        return {"content": content[:8000], "doc_token": token, "char_count": len(content)}
    except Exception as e:
        return {"error": str(e)}


@router.post("/write-cells")
def write_doc_cells(
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    """
    在飞书文档表格中找到含 open_id @mention 的行，更新指定列单元格。
    优先使用当前用户自己的 feishu token（用户有编辑权限即可），降级到机器人 token。
    body: {
      "doc_url": "...",
      "match_open_id": "...",    # 要匹配的 @人 open_id（默认取当前用户）
      "cell_updates": {"列索引(0-based)": "新文本", ...}
    }
    返回: { "updated": N, "details": [...] }
    """
    doc_url = body.get("doc_url", "")
    doc_token = _extract_token(doc_url)
    if not doc_token:
        return {"error": "无效文档链接"}

    match_open_id = body.get("match_open_id") or current_user.get("feishu_open_id", "")
    cell_updates: dict = body.get("cell_updates", {})

    from backend.services import user_service as _us
    user_feishu_token = _us.get_feishu_token(current_user["gid"])

    try:
        if user_feishu_token:
            blocks = _svc.get_doc_blocks_as_user(doc_token, user_feishu_token)
        else:
            blocks = _svc.get_doc_blocks(doc_token)
        result = _update_table_cells(
            doc_token, blocks, match_open_id, cell_updates, user_feishu_token
        )
        return result
    except Exception as e:
        return {"error": str(e)}


def _update_table_cells(
    doc_token: str, blocks: list, match_open_id: str,
    cell_updates: dict, user_feishu_token: str = ""
) -> dict:
    """
    遍历 table block，找到含 match_open_id @mention 的行，
    更新该行中 cell_updates 指定列的 block 文本。
    优先用 user_feishu_token 写入，降级用机器人 token。
    """
    by_id = {b["block_id"]: b for b in blocks}
    table_rows = _parse_table_rows(blocks, by_id)
    updated = 0
    details = []

    for row in table_rows:
        if not _row_has_mention(row, by_id, match_open_id):
            continue
        for col_idx_str, new_text in cell_updates.items():
            col_idx = int(col_idx_str)
            if col_idx < len(row):
                cell_block_id = row[col_idx]
                text_block_id = _get_first_text_block(cell_block_id, by_id)
                if text_block_id:
                    if user_feishu_token:
                        result = _svc.update_block_text_as_user(
                            doc_token, text_block_id, new_text, user_feishu_token
                        )
                    else:
                        result = _svc.update_block_text(doc_token, text_block_id, new_text)
                    details.append({
                        "block_id":    text_block_id,
                        "col":         col_idx,
                        "new_text":    new_text,
                        "result_code": result.get("code", 0),
                    })
                    updated += 1

    return {"updated": updated, "details": details}


def _parse_table_rows(blocks: list, by_id: dict) -> list:
    """
    将 blocks 中的 table 结构按行归组，返回行→列→cell_block_id 二维数组。
    Feishu docx 表格结构：
      block_type=27 (table) → children = [row_block_id, ...]
      block_type=28 (table_row) → children = [cell_block_id, ...]
      block_type=29 (table_cell) → children = [text_block_id, ...]
    """
    rows = []
    for b in blocks:
        if b.get("block_type") == 27:  # table
            for row_id in b.get("children", []):
                row_block = by_id.get(row_id, {})
                if row_block.get("block_type") == 28:
                    rows.append(row_block.get("children", []))
    return rows


def _row_has_mention(row_cells: list, by_id: dict, open_id: str) -> bool:
    """检查一行中任意 cell 的文本是否包含指定 open_id 的 @mention。"""
    for cell_id in row_cells:
        cell = by_id.get(cell_id, {})
        for child_id in cell.get("children", []):
            child = by_id.get(child_id, {})
            for elem in child.get("text", {}).get("elements", []):
                mention = elem.get("mention_user", {})
                if mention.get("user_id") == open_id:
                    return True
    return False


def _get_first_text_block(cell_block_id: str, by_id: dict) -> str | None:
    """从 cell block 取第一个 text block 的 block_id。"""
    cell = by_id.get(cell_block_id, {})
    children = cell.get("children", [])
    return children[0] if children else None
