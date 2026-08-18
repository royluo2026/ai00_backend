"""Deterministic, Craft-shaped large BOP fixtures with exact-GID cleanup metadata."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Callable

from backend.utils.gid import next_gid


NODE_TYPES = (
    "factory_bop", "line_process", "station_process", "operator_process",
    "process", "operation", "part", "tool_need",
)


@dataclass(frozen=True, slots=True)
class BopLargeFixture:
    run_id: str
    root_gid: str
    version_gid: str
    entry_rows: tuple[dict, ...]
    link_rows: tuple[dict, ...]
    identity_gids: tuple[str, ...]

    @property
    def cleanup_batches(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return (
            ("links", tuple(row["gid"] for row in reversed(self.link_rows))),
            ("entries", tuple(row["gid"] for row in reversed(self.entry_rows))),
            ("versions", (self.version_gid,)),
            ("bop_roots", (self.root_gid,)),
            ("identities", tuple(reversed(self.identity_gids))),
        )


def build_large_bop_fixture(
    size: int,
    *,
    run_id: str,
    gid_factory: Callable[[], int | str] = next_gid,
) -> BopLargeFixture:
    if size < 8:
        raise ValueError("size must be at least 8")
    if not run_id or len(run_id) > 64:
        raise ValueError("run_id is required and must not exceed 64 characters")

    def gid() -> str:
        value = str(gid_factory())
        if not value.isdigit() or int(value) <= 0:
            raise ValueError("gid_factory must produce positive snowflake-compatible integers")
        return value

    root_gid = gid()
    version_gid = gid()
    identity_gids = tuple(gid() for _ in range(5))
    rows: list[dict] = []
    links: list[dict] = []
    def add_row(index: int, node_type: str, parent_gid: str | None) -> str:
        entry_gid = gid()
        row = {
            "gid": entry_gid,
            "version_gid": version_gid,
            "parent_gid": parent_gid,
            "node_type": node_type,
            "sort_order": index,
            "title": f"E2E-{run_id}-{index}",
            "meta": {"acceptance_run_id": run_id},
        }
        rows.append(row)
        if node_type in {"operation", "part", "tool_need"}:
            links.append({
                "gid": gid(), "version_gid": version_gid, "entry_gid": entry_gid,
                "link_type": "acceptance_ref", "entity_gid": None,
            })
        return entry_gid

    add_row(0, "factory_bop", None)
    remaining = size - 1
    line_count = min(10, max(1, ceil(remaining / 1000)))
    base_quota, extra = divmod(remaining, line_count)
    index = 1
    for line_index in range(line_count):
        quota = base_quota + (1 if line_index < extra else 0)
        line_gid = add_row(index, "line_process", rows[0]["gid"])
        index += 1
        station_gid = operator_gid = process_gid = None
        sequence = ("station_process", "operator_process", "process", "operation", "part", "tool_need")
        for offset in range(1, quota):
            node_type = sequence[(offset - 1) % len(sequence)]
            if node_type == "station_process":
                parent_gid = line_gid
            elif node_type == "operator_process":
                parent_gid = station_gid or line_gid
            elif node_type == "process":
                parent_gid = operator_gid or station_gid or line_gid
            else:
                parent_gid = process_gid or operator_gid or station_gid or line_gid
            created_gid = add_row(index, node_type, parent_gid)
            if node_type == "station_process": station_gid = created_gid
            elif node_type == "operator_process": operator_gid = created_gid
            elif node_type == "process": process_gid = created_gid
            index += 1

    return BopLargeFixture(
        run_id=run_id,
        root_gid=root_gid,
        version_gid=version_gid,
        entry_rows=tuple(rows),
        link_rows=tuple(links),
        identity_gids=identity_gids,
    )


__all__ = ["BopLargeFixture", "build_large_bop_fixture"]
