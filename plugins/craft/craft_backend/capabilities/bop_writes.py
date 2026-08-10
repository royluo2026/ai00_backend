"""Governed Craft BOP write Capabilities for the Phase 64 safety slice."""
from __future__ import annotations
import copy, hashlib, json, time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Mapping
from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from backend.platform_sdk.ids import next_gid
from ..data.connection import get_craft_conn

_ALLOWED_COMMANDS = frozenset({"entry.create", "entry.update", "entry.archive", "link.attach", "link.detach", "version.metadata.update"})
_ENTRY_FIELDS = frozenset({"parent_gid", "node_type", "sort_order", "title", "vpps", "vpps_desc", "parent_bop_title", "meta"})
_VERSION_FIELDS = frozenset({"version_tag", "bop_name", "change_note", "maturity", "takt_time", "visibility", "data_stage", "pbom_version_gid"})
_SOURCE_KINDS = frozenset({"empty", "bop_version", "template", "import_preview"})
_TTL_SECONDS = 300

def _canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def content_hash(value): return hashlib.sha256(_canonical(value).encode()).hexdigest()
def _now(): return time.time()
def _iso(ts): return datetime.fromtimestamp(ts, timezone.utc).isoformat()
def _db_datetime(value):
    if value is None: return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None: parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
def _epoch(value):
    parsed = _db_datetime(value)
    return parsed.replace(tzinfo=timezone.utc).timestamp()
def _text(payload, name, *, required=False):
    value = payload.get(name)
    if value is None:
        if required: raise ValueError(f"{name} is required")
        return None
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
def _revision(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1: raise CapabilityBusinessError("bop_revision_unavailable", "BOP version has no authoritative revision")
    return value
def _state_hash(version):
    return content_hash({"version": {k: version.get(k) for k in ("gid", "revision", "version_tag", "bop_name", "status", "version_family_gid", "parent_version_gid", "project_gid", "meta")}, "entries": version.get("entries", []), "links": version.get("links", [])})
def _validate_commands(commands):
    if not isinstance(commands, list): raise ValueError("commands must be an array")
    normalized = []
    for command in commands:
        if not isinstance(command, dict): raise ValueError("each command must be an object")
        kind = command.get("kind")
        if kind not in _ALLOWED_COMMANDS: raise ValueError(f"unsupported command kind: {kind}")
        item = copy.deepcopy(command)
        if kind.startswith("entry."):
            data = item.get("entry") if kind == "entry.create" else item.get("changes")
            if not isinstance(data, dict): raise ValueError(f"{kind} requires an object")
            unknown = set(data) - _ENTRY_FIELDS
            if unknown: raise ValueError(f"unsupported entry fields: {', '.join(sorted(unknown))}")
            if kind == "entry.create" and not _text(data, "node_type", required=True): raise ValueError("entry.node_type is required")
            if kind != "entry.create" and not _text(item, "entry_gid", required=True): raise ValueError("entry_gid is required")
        elif kind.startswith("link."):
            for name in ("entry_gid", "link_type", "entity_gid"):
                _text(item, name, required=True)
        else:
            data = item.get("changes")
            if not isinstance(data, dict) or not data: raise ValueError("version.metadata.update requires changes")
            unknown = set(data) - _VERSION_FIELDS
            if unknown: raise ValueError(f"unsupported version fields: {', '.join(sorted(unknown))}")
        normalized.append(item)
    return normalized
def _apply_commands(version, commands, *, allocate_gid):
    result = copy.deepcopy(version); entries = result.setdefault("entries", []); links = result.setdefault("links", [])
    for command in commands:
        kind = command["kind"]
        if kind == "entry.create":
            data = copy.deepcopy(command["entry"]); data["gid"] = str(allocate_gid()); data.setdefault("parent_gid", None); data.setdefault("sort_order", 0); data.setdefault("meta", {}); entries.append(data)
        elif kind == "entry.update":
            target = next((e for e in entries if str(e.get("gid")) == command["entry_gid"]), None)
            if target is None: raise CapabilityBusinessError("bop_entry_not_found", "BOP entry not found")
            target.update(copy.deepcopy(command["changes"]))
        elif kind == "entry.archive":
            target = next((e for e in entries if str(e.get("gid")) == command["entry_gid"]), None)
            if target is None: raise CapabilityBusinessError("bop_entry_not_found", "BOP entry not found")
            target["is_deleted"] = True
        elif kind == "link.attach":
            link = {k: command[k] for k in ("entry_gid", "link_type", "entity_gid")}; link["gid"] = str(allocate_gid()); link["is_primary"] = bool(command.get("is_primary", False)); links.append(link)
        elif kind == "link.detach":
            before = len(links); links[:] = [link for link in links if not (str(link.get("entry_gid")) == command["entry_gid"] and str(link.get("link_type")) == command["link_type"] and str(link.get("entity_gid")) == command["entity_gid"])]
            if len(links) == before: raise CapabilityBusinessError("bop_link_not_found", "BOP link not found")
        elif kind == "version.metadata.update": result.update(copy.deepcopy(command["changes"]))
    return result

class BopWriteRepository:
    def get_version(self, version_gid): raise NotImplementedError
    def save_version(self, version, *, expected_revision): raise NotImplementedError
    def create_version(self, version): raise NotImplementedError
    def issue_confirmation(self, preview_gid, user_gid): raise NotImplementedError
    def consume_confirmation(self, preview_gid, user_gid, token): raise NotImplementedError
    def put_preview(self, preview): raise NotImplementedError
    def get_preview(self, preview_gid): raise NotImplementedError
    def get_preview_by_idempotency(self, version_gid, idempotency_key): return None
    def mark_applied(self, preview_gid, result): raise NotImplementedError
    def get_applied(self, idempotency_key): raise NotImplementedError
    def put_import_preview(self, preview): raise NotImplementedError
    def get_import_preview(self, preview_gid): raise NotImplementedError
    def put_applied(self, idempotency_key, result): raise NotImplementedError
    def commit_preview(self, preview, version, result, *, idempotency_key, actor_id):
        saved = self.save_version(version, expected_revision=preview["base_revision"])
        if idempotency_key: self.put_applied(idempotency_key, result)
        self.mark_applied(preview["preview_gid"], result)
        return saved

class MysqlBopWriteRepository(BopWriteRepository):
    def get_version(self, version_gid):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT gid, project_gid, version_tag, bop_name, version_family_gid, parent_version_gid, revision, status, meta FROM workmanship_bop_bop_versions WHERE gid=%s AND is_deleted=0", (version_gid,)); row = cur.fetchone()
            if not row: return None
            version = dict(row); cur.execute("SELECT gid, parent_gid, node_type, sort_order, title, vpps, vpps_desc, parent_bop_title, meta, is_deleted FROM workmanship_bop_bop_entries WHERE version_gid=%s", (version_gid,)); version["entries"] = [dict(item) for item in cur.fetchall() if not item.get("is_deleted")]; cur.execute("SELECT gid, entry_gid, link_type, entity_gid, is_primary FROM workmanship_bop_bop_entry_links WHERE version_gid=%s AND is_deleted=0", (version_gid,)); version["links"] = [dict(item) for item in cur.fetchall()]; return version
    @staticmethod
    def _json(value):
        if isinstance(value, str):
            try: return json.loads(value)
            except ValueError: return None
        return value

    @staticmethod
    def _write_entries(cur, version):
        version_gid = version["gid"]
        cur.execute(
            "UPDATE workmanship_bop_bop_entries SET is_deleted=1,deleted_at=NOW(6) "
            "WHERE version_gid=%s AND is_deleted=0", (version_gid,),
        )
        for entry in version.get("entries", []):
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entries "
                "(gid,version_gid,parent_gid,node_type,sort_order,title,vpps,vpps_desc,parent_bop_title,meta,is_deleted,deleted_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,NULL) "
                "ON DUPLICATE KEY UPDATE parent_gid=VALUES(parent_gid),node_type=VALUES(node_type),"
                "sort_order=VALUES(sort_order),title=VALUES(title),vpps=VALUES(vpps),"
                "vpps_desc=VALUES(vpps_desc),parent_bop_title=VALUES(parent_bop_title),"
                "meta=VALUES(meta),is_deleted=0,deleted_at=NULL,updated_at=NOW(6)",
                (
                    entry["gid"], version_gid, entry.get("parent_gid"), entry["node_type"],
                    entry.get("sort_order", 0), entry.get("title"), entry.get("vpps"),
                    entry.get("vpps_desc"), entry.get("parent_bop_title"),
                    json.dumps(entry.get("meta") or {}, ensure_ascii=False),
                ),
            )
        cur.execute(
            "UPDATE workmanship_bop_bop_entry_links SET is_deleted=1,deleted_at=NOW(6) "
            "WHERE version_gid=%s AND is_deleted=0", (version_gid,),
        )
        for link in version.get("links", []):
            cur.execute(
                "INSERT INTO workmanship_bop_bop_entry_links "
                "(gid,version_gid,entry_gid,link_type,entity_gid,is_primary,is_deleted,deleted_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,0,NULL) "
                "ON DUPLICATE KEY UPDATE version_gid=VALUES(version_gid),entry_gid=VALUES(entry_gid),"
                "link_type=VALUES(link_type),entity_gid=VALUES(entity_gid),is_primary=VALUES(is_primary),"
                "is_deleted=0,deleted_at=NULL",
                (link["gid"], version_gid, link["entry_gid"], link["link_type"], link["entity_gid"], bool(link.get("is_primary"))),
            )

    def _save_in_transaction(self, cur, version, expected_revision):
        cur.execute(
            "UPDATE workmanship_bop_bop_versions SET version_tag=%s,bop_name=%s,status=%s,"
            "version_family_gid=%s,parent_version_gid=%s,meta=%s,archived_at=%s,revision=revision+1 "
            "WHERE gid=%s AND revision=%s AND is_deleted=0",
            (
                version.get("version_tag") or "", version.get("bop_name") or "",
                version.get("status") or "active", version.get("version_family_gid"),
                version.get("parent_version_gid"), json.dumps(version.get("meta") or {}, ensure_ascii=False),
                _db_datetime(version.get("archived_at")), version["gid"], expected_revision,
            ),
        )
        if cur.rowcount != 1:
            raise CapabilityBusinessError("revision_conflict", "BOP revision does not match expected_revision")
        self._write_entries(cur, version)

    def save_version(self, version, *, expected_revision):
        with get_craft_conn() as conn, conn.cursor() as cur:
            try:
                self._save_in_transaction(cur, version, expected_revision)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        saved = copy.deepcopy(version); saved["revision"] = expected_revision + 1
        return saved

    def create_version(self, version):
        with get_craft_conn() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_versions "
                    "(gid,version_tag,bop_name,status,revision,version_family_gid,parent_version_gid,project_gid,meta,lifecycle_state,created_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        version["gid"], version.get("version_tag") or "", version.get("bop_name") or "",
                        version.get("status") or "active", version.get("revision", 1),
                        version.get("version_family_gid"), version.get("parent_version_gid"),
                        version.get("project_gid"), json.dumps(version.get("meta") or {}, ensure_ascii=False),
                        json.dumps({}, ensure_ascii=False), version.get("created_by"),
                    ),
                )
                self._write_entries(cur, version)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return copy.deepcopy(version)

    def issue_confirmation(self, preview_gid, user_gid):
        raise RuntimeError("confirmation_tokens_are_owned_by_the_capability_gateway")

    def consume_confirmation(self, preview_gid, user_gid, token):
        raise RuntimeError("confirmation_tokens_are_owned_by_the_capability_gateway")

    def put_preview(self, preview):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_craft_bop_change_previews "
                "(gid,version_gid,base_revision,payload_hash,before_hash,after_hash,commands_json,idempotency_key,expires_at,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (preview["preview_gid"], preview["version_gid"], preview["base_revision"], preview["payload_hash"],
                 preview["before_hash"], preview["after_hash"], json.dumps(preview["commands"], ensure_ascii=False),
                 preview.get("idempotency_key"), _db_datetime(preview["expires_at"]), preview["created_by"]),
            )
            conn.commit()

    def get_preview(self, preview_gid):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT gid,version_gid,base_revision,payload_hash,before_hash,after_hash,commands_json,"
                "idempotency_key,expires_at,applied_result_json,created_at FROM workmanship_craft_bop_change_previews WHERE gid=%s",
                (preview_gid,),
            ); row = cur.fetchone()
        if not row: return None
        expires = row["expires_at"]
        expires_epoch = _epoch(expires)
        return {
            "preview_gid": str(row["gid"]), "version_gid": str(row["version_gid"]),
            "base_revision": row["base_revision"], "payload_hash": row["payload_hash"],
            "before_hash": row["before_hash"], "after_hash": row["after_hash"],
            "commands": self._json(row["commands_json"]) or [], "idempotency_key": row.get("idempotency_key"),
            "expires_at": expires.isoformat() if hasattr(expires, "isoformat") else str(expires),
            "expires_at_epoch": expires_epoch, "applied": self._json(row.get("applied_result_json")),
        }

    def get_preview_by_idempotency(self, version_gid, idempotency_key):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT gid FROM workmanship_craft_bop_change_previews "
                "WHERE version_gid=%s AND idempotency_key=%s",
                (version_gid, idempotency_key),
            ); row = cur.fetchone()
        return self.get_preview(str(row["gid"])) if row else None

    def mark_applied(self, preview_gid, result):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_craft_bop_change_previews SET applied_result_json=%s WHERE gid=%s AND applied_result_json IS NULL",
                (json.dumps(result, ensure_ascii=False), preview_gid),
            ); conn.commit()

    def get_applied(self, idempotency_key):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT result_json FROM workmanship_craft_bop_write_idempotency WHERE idempotency_key=%s", (idempotency_key,)); row = cur.fetchone()
        return self._json(row["result_json"]) if row else None

    def put_import_preview(self, preview):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_craft_bop_import_previews "
                "(gid,content_sha256,document_json,entry_count,expires_at,created_by) VALUES (%s,%s,%s,%s,%s,%s)",
                (preview["import_preview_gid"], preview["content_hash"], json.dumps(preview["document"], ensure_ascii=False),
                 preview["entry_count"], _db_datetime(preview["expires_at"]), preview["created_by"]),
            ); conn.commit()

    def get_import_preview(self, preview_gid):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT document_json FROM workmanship_craft_bop_import_previews "
                "WHERE gid=%s AND expires_at>NOW(6)", (preview_gid,),
            ); row = cur.fetchone()
        document = self._json(row["document_json"]) if row else None
        return dict(document) if isinstance(document, Mapping) else None

    def put_applied(self, idempotency_key, result):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_craft_bop_write_idempotency "
                "(idempotency_key,capability_id,version_gid,result_json,created_by) VALUES (%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key",
                (idempotency_key, "craft.bop.draft.change.apply", result.get("version_gid"),
                 json.dumps(result, ensure_ascii=False), "capability-gateway"),
            ); conn.commit()

    def commit_preview(self, preview, version, result, *, idempotency_key, actor_id):
        with get_craft_conn() as conn, conn.cursor() as cur:
            try:
                self._save_in_transaction(cur, version, preview["base_revision"])
                cur.execute(
                    "UPDATE workmanship_craft_bop_change_previews SET applied_result_json=%s "
                    "WHERE gid=%s AND applied_result_json IS NULL",
                    (json.dumps(result, ensure_ascii=False), preview["preview_gid"]),
                )
                if cur.rowcount != 1:
                    raise CapabilityBusinessError("preview_already_applied", "BOP change preview was already applied")
                if idempotency_key:
                    cur.execute(
                        "INSERT INTO workmanship_craft_bop_write_idempotency "
                        "(idempotency_key,capability_id,version_gid,result_json,created_by) VALUES (%s,%s,%s,%s,%s)",
                        (idempotency_key, "craft.bop.draft.change.apply", result.get("version_gid"),
                         json.dumps(result, ensure_ascii=False), actor_id),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return copy.deepcopy(version)

@dataclass
class _MemoryWriteRepository(BopWriteRepository):
    versions: dict = field(default_factory=dict); previews: dict = field(default_factory=dict); applied: dict = field(default_factory=dict); imports: dict = field(default_factory=dict); tokens: dict = field(default_factory=dict)
    def get_version(self, version_gid): return self.versions.get(version_gid)
    def save_version(self, version, *, expected_revision):
        current = self.versions[version["gid"]]
        if current["revision"] != expected_revision: raise CapabilityBusinessError("revision_conflict", "revision conflict")
        version = copy.deepcopy(version); version["revision"] = expected_revision + 1; self.versions[version["gid"]] = version; return version
    def create_version(self, version): self.versions[version["gid"]] = copy.deepcopy(version); return self.versions[version["gid"]]
    def issue_confirmation(self, preview_gid, user_gid): token = f"confirm:{preview_gid}:{user_gid}"; self.tokens[(preview_gid, user_gid)] = token; return token
    def consume_confirmation(self, preview_gid, user_gid, token): return self.tokens.pop((preview_gid, user_gid), None) == token
    def put_preview(self, preview): self.previews[preview["preview_gid"]] = copy.deepcopy(preview)
    def get_preview(self, preview_gid): return self.previews.get(preview_gid)
    def get_preview_by_idempotency(self, version_gid, idempotency_key):
        return next((item for item in self.previews.values() if item["version_gid"] == version_gid and item.get("idempotency_key") == idempotency_key), None)
    def mark_applied(self, preview_gid, result): self.previews[preview_gid]["applied"] = copy.deepcopy(result)
    def get_applied(self, idempotency_key): return self.applied.get(idempotency_key)
    def put_import_preview(self, preview): self.imports[preview["import_preview_gid"]] = copy.deepcopy(preview)
    def get_import_preview(self, preview_gid):
        preview = self.imports.get(preview_gid)
        return copy.deepcopy(preview.get("document")) if preview else None
    def put_applied(self, idempotency_key, result): self.applied[idempotency_key] = copy.deepcopy(result)

repository: BopWriteRepository = MysqlBopWriteRepository()
def _preview_data(version_gid, before, after, commands, expected_revision, idempotency_key, created_by):
    created = _now(); return {"preview_gid": str(next_gid()), "version_gid": version_gid, "base_revision": expected_revision, "commands": commands, "before_hash": _state_hash(before), "after_hash": _state_hash(after), "payload_hash": content_hash({"version_gid": version_gid, "expected_revision": expected_revision, "commands": commands}), "idempotency_key": idempotency_key, "created_by": created_by, "created_at": _iso(created), "expires_at": _iso(created + _TTL_SECONDS), "expires_at_epoch": created + _TTL_SECONDS}
def preview_draft_change(payload, context):
    version_gid = _text(payload, "version_gid", required=True); expected_revision = payload.get("expected_revision")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int): raise ValueError("expected_revision must be an integer")
    commands = _validate_commands(payload.get("commands")); idempotency_key = _text(payload, "idempotency_key")
    payload_hash = content_hash({"version_gid": version_gid, "expected_revision": expected_revision, "commands": commands})
    if idempotency_key:
        existing = repository.get_preview_by_idempotency(version_gid, idempotency_key)
        if existing is not None:
            if existing.get("payload_hash") != payload_hash:
                raise CapabilityBusinessError("idempotency_conflict", "Preview idempotency key is bound to another payload")
            return CapabilityOutput(
                data={k: v for k, v in existing.items() if k not in {"expires_at_epoch", "created_by", "applied"}},
                evidence=(EvidenceRef(kind="craft.bop.preview", reference=f"craft://bop/preview/{existing['preview_gid']}", digest=existing["after_hash"]),),
            )
    before = repository.get_version(version_gid)
    if before is None: raise CapabilityBusinessError("bop_version_not_found", "BOP version not found")
    if _revision(before.get("revision")) != expected_revision: raise CapabilityBusinessError("revision_conflict", "BOP revision does not match expected_revision")
    after = _apply_commands(before, commands, allocate_gid=lambda: "preview-gid"); preview = _preview_data(version_gid, before, after, commands, expected_revision, idempotency_key, context.user_gid); repository.put_preview(preview)
    return CapabilityOutput(data={k: v for k, v in preview.items() if k not in {"expires_at_epoch", "created_by"}}, evidence=(EvidenceRef(kind="craft.bop.preview", reference=f"craft://bop/preview/{preview['preview_gid']}", digest=preview["after_hash"]),))
def apply_draft_change(payload, context):
    preview_gid = _text(payload, "preview_gid", required=True); idempotency_key = _text(payload, "idempotency_key")
    if idempotency_key:
        applied = repository.get_applied(idempotency_key)
        if applied is not None: return CapabilityOutput(data=applied)
    preview = repository.get_preview(preview_gid)
    if not preview: raise CapabilityBusinessError("preview_not_found", "BOP change preview not found")
    if preview.get("applied") is not None: return CapabilityOutput(data=preview["applied"])
    bound_idempotency_key = preview.get("idempotency_key")
    if bound_idempotency_key and idempotency_key and bound_idempotency_key != idempotency_key:
        raise CapabilityBusinessError("idempotency_conflict", "Apply idempotency key differs from the preview binding")
    idempotency_key = idempotency_key or bound_idempotency_key
    if preview.get("expires_at_epoch", 0) <= _now(): raise CapabilityBusinessError("preview_expired", "BOP change preview has expired")
    version = repository.get_version(preview["version_gid"])
    if not version: raise CapabilityBusinessError("bop_version_not_found", "BOP version not found")
    if _revision(version.get("revision")) != preview["base_revision"]: raise CapabilityBusinessError("revision_conflict", "BOP revision changed after preview")
    before_hash = _state_hash(version)
    after = _apply_commands(version, preview["commands"], allocate_gid=next_gid)
    after["revision"] = preview["base_revision"] + 1
    result = {"version_gid": after["gid"], "revision": after["revision"], "before_hash": before_hash, "after_hash": _state_hash(after), "preview_gid": preview_gid, "idempotency_key": idempotency_key}
    saved = repository.commit_preview(
        preview, after, result, idempotency_key=idempotency_key, actor_id=context.user_gid
    )
    return CapabilityOutput(data=result, evidence=(EvidenceRef(kind="craft.bop.version", reference=f"craft://bop/version/{saved['gid']}", digest=result["after_hash"]),))
def create_bop_version(payload, context):
    source = _text(payload, "source", required=True)
    if source not in _SOURCE_KINDS: raise ValueError(f"unsupported source: {source}")
    version_tag = _text(payload, "version_tag", required=True); source_version = None
    if source == "bop_version": source_version = repository.get_version(_text(payload, "source_gid", required=True))
    elif source == "template": source_version = repository.get_version(_text(payload, "template_gid", required=True))
    elif source == "import_preview": source_version = repository.get_import_preview(_text(payload, "import_preview_gid", required=True))
    if source != "empty" and source_version is None: raise CapabilityBusinessError("source_not_found", "Creation source not found")
    source_version = source_version or {"entries": [], "links": [], "meta": {}}
    version_gid = str(next_gid())
    version = copy.deepcopy(source_version)
    version.update({
        "gid": version_gid,
        "version_tag": version_tag,
        "status": "active",
        "revision": 1,
        "parent_version_gid": source_version.get("gid"),
        "version_family_gid": _text(payload, "version_family_gid") or version_gid,
        "created_by": context.user_gid,
    })
    source_entries = list(version.get("entries", []))
    new_entry_gids = [str(next_gid()) for _item in source_entries]
    gid_map = {
        str(item["gid"]): new_entry_gids[index]
        for index, item in enumerate(source_entries)
        if item.get("gid") is not None
    }
    version["entries"] = [
        {
            **item,
            "gid": new_entry_gids[index],
            "parent_gid": gid_map.get(str(item.get("parent_gid"))) if item.get("parent_gid") else None,
        }
        for index, item in enumerate(source_entries)
    ]
    version["links"] = []
    created = repository.create_version(version)
    return CapabilityOutput(data={"version_gid": created["gid"], "status": created["status"], "revision": created["revision"], "parent_version_gid": created.get("parent_version_gid"), "entries_count": len(created.get("entries", []))}, evidence=(EvidenceRef(kind="craft.bop.version", reference=f"craft://bop/version/{created['gid']}", digest=_state_hash(created)),))
def archive_bop_version(payload, _context):
    version_gid = _text(payload, "version_gid", required=True); expected_revision = payload.get("expected_revision")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int): raise ValueError("expected_revision must be an integer")
    version = repository.get_version(version_gid)
    if not version: raise CapabilityBusinessError("bop_version_not_found", "BOP version not found")
    if version.get("status") in {"M", "published"}: raise CapabilityBusinessError("archive_forbidden", "Published BOP versions cannot be archived")
    if _revision(version.get("revision")) != expected_revision: raise CapabilityBusinessError("revision_conflict", "BOP revision does not match expected_revision")
    before_hash = _state_hash(version); changed = copy.deepcopy(version); changed["status"] = "archived"; changed["archived_at"] = _iso(_now()); saved = repository.save_version(changed, expected_revision=expected_revision)
    return CapabilityOutput(data={"version_gid": version_gid, "status": saved["status"], "revision": saved["revision"], "before_hash": before_hash, "after_hash": _state_hash(saved)}, evidence=(EvidenceRef(kind="craft.bop.version", reference=f"craft://bop/version/{version_gid}", digest=_state_hash(saved)),))
def import_preview(payload, context):
    document = payload.get("document")
    if not isinstance(document, dict): raise ValueError("document must be an object")
    entries = document.get("entries", [])
    if not isinstance(entries, list): raise ValueError("document.entries must be an array")
    normalized = {"version_tag": document.get("version_tag"), "bop_name": document.get("bop_name"), "entries": copy.deepcopy(entries)}; digest = content_hash(normalized); preview = {"import_preview_gid": str(next_gid()), "content_hash": digest, "entry_count": len(entries), "document": normalized, "created_by": context.user_gid, "expires_at": _iso(_now() + _TTL_SECONDS)}
    repository.put_import_preview(preview)
    return CapabilityOutput(data={k: v for k, v in preview.items() if k not in {"document", "created_by"}}, evidence=(EvidenceRef(kind="craft.bop.import", reference=f"craft://bop/import/{preview['import_preview_gid']}", digest=digest),))
def register_bop_write_capabilities(registry):
    common = {"owner": "craft", "plugin_callable": False, "permissions": ("craft.write",), "tags": ("craft", "bop", "write")}
    registry.register(CapabilitySpec(id="craft.bop.draft.change.preview", description="Preview a typed BOP draft change without side effects.", risk="read", input_schema={"type": "object", "required": ["version_gid", "expected_revision", "commands"]}, output_schema={"type": "object", "required": ["preview_gid", "version_gid", "base_revision", "before_hash", "after_hash", "expires_at"]}, **common), preview_draft_change)
    registry.register(CapabilitySpec(id="craft.bop.draft.change.apply", description="Apply one exact typed BOP draft preview atomically.", risk="write", confirmation="user", idempotent=True, input_schema={"type": "object", "required": ["preview_gid"]}, output_schema={"type": "object", "required": ["version_gid", "revision", "before_hash", "after_hash"]}, **common), apply_draft_change)
    registry.register(CapabilitySpec(id="craft.bop.version.create", description="Create a BOP draft from an empty, version, template or import preview source.", risk="write", confirmation="user", idempotent=False, input_schema={"type": "object", "required": ["source", "version_tag"]}, output_schema={"type": "object", "required": ["version_gid", "status", "revision", "entries_count"]}, **common), create_bop_version)
    registry.register(CapabilitySpec(id="craft.bop.version.archive", description="Archive a BOP version without deleting its snapshot or references.", risk="write", confirmation="user", idempotent=True, input_schema={"type": "object", "required": ["version_gid", "expected_revision"]}, output_schema={"type": "object", "required": ["version_gid", "status", "revision", "before_hash", "after_hash"]}, **common), archive_bop_version)
    registry.register(CapabilitySpec(id="craft.bop.import.preview", description="Parse and hash a BOP import document without mutating Craft state.", risk="read", input_schema={"type": "object", "required": ["document"]}, output_schema={"type": "object", "required": ["import_preview_gid", "content_hash", "entry_count", "expires_at"]}, **common), import_preview)
