# backend/services/bitable_sync_service.py
"""
飞书多维表格（Bitable）同步服务。
封装飞书 Bitable v1 REST API，提供 LWW 合并逻辑。
使用 tenant_access_token（不依赖 user_access_token）。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from backend.db.connection import get_conn
from backend.services.feishu_service import feishu_service

_log = logging.getLogger(__name__)
FEISHU_API = "https://open.feishu.cn/open-apis"


class BitableSyncService:

    # ── 飞书 Bitable API ──────────────────────────────────────────────────────

    def _token(self) -> str:
        return feishu_service._get_tenant_token()

    def get_table_schema(self, app_token: str, table_id: str, token: str = None) -> list[dict]:
        """返回多维表格字段列表，每项含 field_id + field_name + type。"""
        if token is None:
            token = self._token()
        resp = requests.get(
            f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": 100},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"get_table_schema failed: {data.get('msg')}")
        return data.get("data", {}).get("items", [])

    def get_record(self, app_token: str, table_id: str, record_id: str, token: str = None) -> dict:
        if token is None:
            token = self._token()
        resp = requests.get(
            f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"get_record failed: {data.get('msg')}")
        return data.get("data", {}).get("record", {})

    def create_record(self, app_token: str, table_id: str, fields: dict, token: str = None) -> str:
        """创建记录，返回 record_id。"""
        if token is None:
            token = self._token()
        resp = requests.post(
            f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": fields},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"create_record failed: {data.get('msg')}")
        return data["data"]["record"]["record_id"]

    def update_record(self, app_token: str, table_id: str, record_id: str, fields: dict, token: str = None) -> None:
        if token is None:
            token = self._token()
        resp = requests.put(
            f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": fields},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"update_record failed: {data.get('msg')}")

    def delete_record(self, app_token: str, table_id: str, record_id: str, token: str = None) -> None:
        if token is None:
            token = self._token()
        resp = requests.delete(
            f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"delete_record failed: {data.get('msg')}")

    def list_records(self, app_token: str, table_id: str, token: str = None) -> list[dict]:
        """全量拉取所有记录（自动翻页）。"""
        if token is None:
            token = self._token()
        records = []
        page_token = ""
        while True:
            params: dict = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(
                f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise ValueError(f"list_records failed: {data.get('msg')}")
            items = data.get("data", {}).get("items", [])
            records.extend(items)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token", "")
        return records

    # ── 字段转换 ──────────────────────────────────────────────────────────────

    def ai00_to_feishu_fields(self, row: dict, mapping: dict) -> dict:
        """将 AI00 行字段按 mapping 映射为飞书字段。跳过 None 值。"""
        result = {}
        for ai00_field, feishu_field_id in mapping.items():
            if not feishu_field_id:
                continue
            val = row.get(ai00_field)
            if val is None:
                continue
            result[feishu_field_id] = val
        return result

    def feishu_to_ai00_fields(self, record_fields: dict, mapping: dict) -> dict:
        """将飞书 record.fields 按 mapping 反向映射为 AI00 字段。"""
        reverse = {v: k for k, v in mapping.items() if v}
        result = {}
        for feishu_field_id, cell in record_fields.items():
            ai00_field = reverse.get(feishu_field_id)
            if not ai00_field:
                continue
            val = cell.get("value") if isinstance(cell, dict) else cell
            result[ai00_field] = val
        return result

    # ── LWW 核心 ─────────────────────────────────────────────────────────────

    def _lww_winner(
        self,
        ai00_ts: Optional[datetime],
        feishu_ts: Optional[datetime],
    ) -> str:
        """返回 'ai00' | 'feishu' | 'skip'。"""
        if ai00_ts is None and feishu_ts is None:
            return "ai00"   # 新条目，推送
        if feishu_ts is None:
            return "ai00"
        if ai00_ts is None:
            return "feishu"
        if ai00_ts > feishu_ts:
            return "ai00"
        if feishu_ts > ai00_ts:
            return "feishu"
        return "skip"

    def _get_binding(self, conn, list_gid: str) -> Optional[dict]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_work_list_bitable_bindings "
                "WHERE list_gid=%s AND is_deleted=FALSE AND sync_enabled=TRUE",
                (list_gid,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def _get_record_map_entry(self, conn, list_gid: str, item_gid: str) -> Optional[dict]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_work_list_bitable_record_map "
                "WHERE list_gid=%s AND item_gid=%s AND is_deleted=FALSE",
                (list_gid, item_gid),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def _upsert_record_map(
        self, conn, list_gid: str, item_gid: str,
        record_id: str, ai00_ts: Optional[datetime], feishu_ts: Optional[datetime],
    ) -> None:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO workmanship_work_list_bitable_record_map
                    (list_gid, item_gid, record_id, ai00_updated_at, feishu_updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    record_id         = VALUES(record_id),
                    ai00_updated_at   = VALUES(ai00_updated_at),
                    feishu_updated_at = VALUES(feishu_updated_at),
                    is_deleted        = FALSE,
                    deleted_at        = NULL
            """, (list_gid, item_gid, record_id, ai00_ts, feishu_ts))

    # ── 推送：AI00 → 飞书 ────────────────────────────────────────────────────

    def push_rows(self, list_gid: str, rows: list[dict]) -> dict:
        """
        增量推送 AI00 行到飞书多维表格。
        rows 中每行须含 gid 和 updated_at（ISO 字符串或 datetime）。
        返回 {pushed: int, skipped: int, errors: list[str]}。
        """
        result = {"pushed": 0, "skipped": 0, "errors": []}
        with get_conn() as conn:
            binding = self._get_binding(conn, list_gid)
            if not binding:
                return result
            app_token = binding["app_token"]
            table_id = binding["table_id"]
            mapping = dict(binding["field_mapping"]) if binding["field_mapping"] else {}
            if not mapping:
                return result

            token = self._token()   # fetch once for the whole batch
            for row in rows:
                item_gid = row.get("gid")
                if not item_gid:
                    continue
                try:
                    ai00_ts = row.get("updated_at")
                    if isinstance(ai00_ts, str):
                        ai00_ts = datetime.fromisoformat(ai00_ts.replace("Z", "+00:00"))

                    map_entry = self._get_record_map_entry(conn, list_gid, item_gid)
                    winner = self._lww_winner(
                        ai00_ts,
                        map_entry["feishu_updated_at"] if map_entry else None,
                    )
                    if winner == "skip":
                        result["skipped"] += 1
                        continue
                    if winner == "feishu":
                        result["skipped"] += 1
                        continue

                    fields = self.ai00_to_feishu_fields(row, mapping)
                    if not fields:
                        result["skipped"] += 1
                        continue

                    if map_entry and map_entry.get("record_id"):
                        self.update_record(app_token, table_id, map_entry["record_id"], fields, token=token)
                        record_id = map_entry["record_id"]
                    else:
                        record_id = self.create_record(app_token, table_id, fields, token=token)

                    self._upsert_record_map(conn, list_gid, item_gid, record_id, ai00_ts, None)
                    result["pushed"] += 1
                except Exception as e:
                    _log.error("push_rows item_gid=%s error: %s", item_gid, e)
                    result["errors"].append(str(e))

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_work_list_bitable_bindings SET last_push_at=NOW() WHERE list_gid=%s",
                    (list_gid,),
                )
            conn.commit()
        return result

    def push_all(self, list_gid: str, all_rows: list[dict]) -> dict:
        """全量推送：与 push_rows 相同逻辑，处理所有行。"""
        return self.push_rows(list_gid, all_rows)

    # ── 拉取：飞书 → AI00 ────────────────────────────────────────────────────

    def pull_all(self, list_gid: str, item_type: str) -> dict:
        """
        全量从飞书拉取，LWW 判断胜出方。
        返回 {pulled: int, skipped: int, errors: list[str], records_to_apply: list[dict]}。
        records_to_apply 中每项含 record_id, item_gid, fields, feishu_updated_at，
        由调用方（router pull 端点）负责写入业务表并清除 has_remote_updates 标志。
        """
        result: dict = {"pulled": 0, "skipped": 0, "errors": [], "records_to_apply": []}
        with get_conn() as conn:
            binding = self._get_binding(conn, list_gid)
            if not binding:
                return result
            app_token = binding["app_token"]
            table_id = binding["table_id"]
            mapping = dict(binding["field_mapping"]) if binding["field_mapping"] else {}
            if not mapping:
                return result

            token = self._token()   # fetch once for the whole pull
            try:
                records = self.list_records(app_token, table_id, token=token)
            except Exception as e:
                _log.error("pull_all list_records error: %s", e)
                result["errors"].append(str(e))
                return result

            # 建 record_id → map_entry 反查表
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT item_gid, record_id, feishu_updated_at, ai00_updated_at "
                    "FROM workmanship_work_list_bitable_record_map "
                    "WHERE list_gid=%s AND is_deleted=FALSE",
                    (list_gid,),
                )
                existing = {r["record_id"]: dict(r) for r in cur.fetchall()}

            for rec in records:
                record_id = rec.get("record_id", "")
                feishu_ts_ms = rec.get("last_modified_time")  # 毫秒时间戳
                feishu_ts = (
                    datetime.fromtimestamp(feishu_ts_ms / 1000, tz=timezone.utc)
                    if feishu_ts_ms else None
                )
                try:
                    map_entry = existing.get(record_id)
                    winner = self._lww_winner(
                        map_entry["ai00_updated_at"] if map_entry else None,
                        feishu_ts,
                    )
                    if winner != "feishu":
                        result["skipped"] += 1
                        continue
                    fields = self.feishu_to_ai00_fields(rec.get("fields", {}), mapping)
                    result["records_to_apply"].append({
                        "record_id": record_id,
                        "item_gid": map_entry["item_gid"] if map_entry else None,
                        "fields": fields,
                        "feishu_updated_at": feishu_ts,
                    })
                    result["pulled"] += 1
                except Exception as e:
                    _log.error("pull_all record=%s error: %s", record_id, e)
                    result["errors"].append(str(e))

            # Only update last_pull_at; caller is responsible for clearing has_remote_updates
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_work_list_bitable_bindings "
                    "SET last_pull_at=NOW() "
                    "WHERE list_gid=%s",
                    (list_gid,),
                )
            conn.commit()
        return result

    # ── Webhook 处理：飞书 → AI00 ────────────────────────────────────────────

    def handle_webhook_event(self, event: dict) -> None:
        """
        处理飞书多维表格 Webhook 事件（在后台线程中调用）。
        支持 bitable.record.created / updated / deleted。
        仅设置 has_remote_updates=true，前端轮询后触发实际 pull。
        """
        try:
            event_type = event.get("header", {}).get("event_type", "")
            if not event_type.startswith("bitable.record."):
                return
            obj = event.get("event", {})
            app_token = obj.get("app_token", "")
            table_id = obj.get("table_id", "")
            if not app_token or not table_id:
                return

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE workmanship_work_list_bitable_bindings "
                        "SET has_remote_updates=TRUE "
                        "WHERE app_token=%s AND table_id=%s AND is_deleted=FALSE",
                        (app_token, table_id),
                    )
                conn.commit()
            _log.info("handle_webhook_event: marked has_remote_updates for %s/%s", app_token, table_id)
        except Exception as e:
            _log.error("handle_webhook_event error: %s", e)


bitable_sync_service = BitableSyncService()
