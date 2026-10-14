"""Transport-neutral Project Management value objects."""
from __future__ import annotations

import json
from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Callable


@dataclass(frozen=True)
class ProjectObjectRef:
    object_ref: str
    title: str
    owner: str = "project_management"

    def __post_init__(self) -> None:
        if not self.object_ref or ":" not in self.object_ref:
            raise ValueError("object_ref must be a typed Project Management reference")
        if not self.title.strip():
            raise ValueError("title is required")


class OrgManagementError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _decode_meta_root(meta: Any) -> dict[str, Any]:
    if isinstance(meta, str):
        if not meta.strip():
            return {}
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError as exc:
            raise OrgManagementError("invalid_state", "项目元数据损坏") from exc
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise OrgManagementError("invalid_state", "项目元数据损坏")
    return meta


def decode_org_management(meta: Any) -> dict[str, Any]:
    root = _decode_meta_root(meta)
    raw = root.get("org_management")
    if not isinstance(raw, dict):
        return {"revision": 0, "lines": []}
    revision = raw.get("revision", 0)
    lines = raw.get("lines", [])
    if not isinstance(revision, int) or revision < 0 or not isinstance(lines, list):
        raise OrgManagementError("invalid_state", "项目责任配置损坏")
    return {"revision": revision, "lines": deepcopy(lines)}


def _leaders(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise OrgManagementError("invalid_input", "线体负责人必须是数组")
    result = sorted({str(value).strip() for value in values if str(value).strip()})
    if len(result) > 50:
        raise OrgManagementError("invalid_input", "每条线体最多 50 位负责人")
    return result


def _validate_lines(lines: list[dict[str, Any]]) -> None:
    names = [str(line["name"]).strip() for line in lines]
    mappings = [line.get("bop_line_gid") for line in lines if line.get("bop_line_gid")]
    if len(names) != len(set(names)):
        raise OrgManagementError("invalid_input", "同一项目内线体名称不能重复")
    if len(mappings) != len(set(mappings)):
        raise OrgManagementError("invalid_input", "同一 BOP 线体不能重复映射")


def apply_line_change(meta: Any, *, operation: str, arguments: dict[str, Any],
                      expected_revision: int, new_gid: Callable[[], str]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    root = deepcopy(_decode_meta_root(meta))
    state = decode_org_management(root)
    if state["revision"] != expected_revision:
        raise OrgManagementError("version_conflict", "项目责任配置已被其他人修改")
    lines = state["lines"]
    selected: dict[str, Any] | None = None
    if operation == "managed_line.assign":
        gids = arguments.get("line_gids", [])
        if not isinstance(gids, list) or not 1 <= len(gids) <= 100 or len(set(gids)) != len(gids):
            raise OrgManagementError("invalid_input", "请选择 1 至 100 条线体")
        targets = [line for line in lines if line["gid"] in gids]
        if len(targets) != len(gids):
            raise OrgManagementError("resource_not_found", "选中的线体已不存在")
        people = _leaders(arguments.get("leader_user_gids", []))
        if not people:
            raise OrgManagementError("invalid_input", "请选择负责人")
        for line in targets:
            line["leader_user_gids"] = _leaders(line["leader_user_gids"] + people)
        selected = {"lines": targets}
    elif operation == "managed_line.sync":
        targets = []
        claimed = set()
        original_mappings = {line["gid"]: line.get("bop_line_gid") for line in lines}
        for source in arguments.get("bop_lines", []):
            identity = {source["gid"], *source.get("ancestor_gids", [])}
            matches = [line for line in lines if original_mappings.get(line["gid"]) in identity]
            if len(matches) > 1 or (matches and matches[0]["gid"] in claimed):
                raise OrgManagementError("invalid_input", "BOP 来源关系存在多条映射，请先检查绑定")
            if matches:
                target = matches[0]
                claimed.add(target["gid"])
                target["bop_line_gid"] = source["gid"]
            else:
                name = str(source.get("title") or source["gid"]).strip()
                if any(line["name"] == name for line in lines):
                    name = f'{name} ({source["gid"]})'
                target = {"gid": new_gid(), "name": name, "leader_user_gids": [], "bop_line_gid": source["gid"]}
                lines.append(target)
            targets.append(target)
        selected = {"lines": targets}
    elif operation == "managed_line.create":
        name = str(arguments.get("name") or "").strip()
        if not name:
            raise OrgManagementError("invalid_input", "线体名称不能为空")
        selected = {"gid": new_gid(), "name": name,
                    "leader_user_gids": _leaders(arguments.get("leader_user_gids", [])),
                    "bop_line_gid": str(arguments["bop_line_gid"]).strip() if arguments.get("bop_line_gid") else None}
        lines.append(selected)
    elif operation == "managed_line.update":
        line_gid = str(arguments.get("line_gid") or "")
        selected = next((line for line in lines if line.get("gid") == line_gid), None)
        if selected is None:
            raise OrgManagementError("resource_not_found", "线体不存在")
        if "name" in arguments:
            name = str(arguments.get("name") or "").strip()
            if not name:
                raise OrgManagementError("invalid_input", "线体名称不能为空")
            selected["name"] = name
        if "leader_user_gids" in arguments:
            selected["leader_user_gids"] = _leaders(arguments["leader_user_gids"])
        if "bop_line_gid" in arguments:
            selected["bop_line_gid"] = (str(arguments["bop_line_gid"]).strip()
                                         if arguments["bop_line_gid"] else None)
    elif operation == "managed_line.delete":
        line_gid = str(arguments.get("line_gid") or "")
        index = next((i for i, line in enumerate(lines) if line.get("gid") == line_gid), None)
        if index is None:
            raise OrgManagementError("resource_not_found", "线体不存在")
        selected = lines.pop(index)
    else:
        raise OrgManagementError("invalid_input", "不支持的线体操作")
    _validate_lines(lines)
    if len(lines) > 5000:
        raise OrgManagementError("invalid_input", "项目线体最多 5000 条")
    root["org_management"] = {"revision": expected_revision + 1,
                               "lines": sorted(lines, key=lambda item: (item["name"], item["gid"]))}
    return root, deepcopy(selected)


__all__ = ["OrgManagementError", "ProjectObjectRef", "apply_line_change", "decode_org_management"]
