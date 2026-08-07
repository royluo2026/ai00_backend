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
    def mark_applied(self, preview_gid, result): raise NotImplementedError
    def get_applied(self, idempotency_key): raise NotImplementedError
    def put_import_preview(self, preview): raise NotImplementedError
    def put_applied(self, idempotency_key, result): raise NotImplementedError

class MysqlBopWriteRepository(BopWriteRepository):
    def get_version(self, version_gid):
        with get_craft_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT gid, project_gid, version_tag, bop_name, version_family_gid, parent_version_gid, revision, status, meta FROM workmanship_bop_bop_versions WHERE gid=%s AND is_deleted=0", (version_gid,)); row = cur.fetchone()
            if not row: return None
            version = dict(row); cur.execute("SELECT gid, parent_gid, node_type, sort_order, title, vpps, vpps_desc, parent_bop_title, meta, is_deleted FROM workmanship_bop_bop_entries WHERE version_gid=%s", (version_gid,)); version["entries"] = [dict(item) for item in cur.fetchall() if not item.get("is_deleted")]; cur.execute("SELECT gid, entry_gid, link_type, entity_gid, is_primary FROM workmanship_bop_bop_entry_links WHERE version_gid=%s AND is_deleted=0", (version_gid,)); version["links"] = [dict(item) for item in cur.fetchall()]; return version
    def save_version(self, version, *, expected_revision): raise NotImplementedError("live write repository will be enabled after preview migration")
    def create_version(self, version): raise NotImplementedError("live write repository will be enabled after preview migration")
    def issue_confirmation(self, preview_gid, user_gid): raise NotImplementedError("live confirmation persistence is pending")
    def consume_confirmation(self, preview_gid, user_gid, token): raise NotImplementedError("live confirmation persistence is pending")
    def put_preview(self, preview): raise NotImplementedError("preview persistence migration required before live write acceptance")
    def get_preview(self, preview_gid): raise NotImplementedError("preview persistence migration required before live write acceptance")
    def mark_applied(self, preview_gid, result): raise NotImplementedError("preview persistence migration required before live write acceptance")
    def get_applied(self, idempotency_key): raise NotImplementedError("idempotency persistence migration required before live write acceptance")
    def put_import_preview(self, preview): raise NotImplementedError
    def put_applied(self, idempotency_key, result): raise NotImplementedError("import preview persistence migration required before live write acceptance")

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
    def mark_applied(self, preview_gid, result): self.previews[preview_gid]["applied"] = copy.deepcopy(result)
    def get_applied(self, idempotency_key): return self.applied.get(idempotency_key)
    def put_import_preview(self, preview): self.imports[preview["import_preview_gid"]] = copy.deepcopy(preview)
    def put_applied(self, idempotency_key, result): self.applied[idempotency_key] = copy.deepcopy(result)

repository: BopWriteRepository = MysqlBopWriteRepository()
def _preview_data(version_gid, before, after, commands, expected_revision, idempotency_key):
    created = _now(); return {"preview_gid": str(next_gid()), "version_gid": version_gid, "base_revision": expected_revision, "commands": commands, "before_hash": _state_hash(before), "after_hash": _state_hash(after), "payload_hash": content_hash({"version_gid": version_gid, "expected_revision": expected_revision, "commands": commands}), "idempotency_key": idempotency_key, "created_at": _iso(created), "expires_at": _iso(created + _TTL_SECONDS), "expires_at_epoch": created + _TTL_SECONDS}
def preview_draft_change(payload, _context):
    version_gid = _text(payload, "version_gid", required=True); expected_revision = payload.get("expected_revision")
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int): raise ValueError("expected_revision must be an integer")
    commands = _validate_commands(payload.get("commands")); before = repository.get_version(version_gid)
    if before is None: raise CapabilityBusinessError("bop_version_not_found", "BOP version not found")
    if _revision(before.get("revision")) != expected_revision: raise CapabilityBusinessError("revision_conflict", "BOP revision does not match expected_revision")
    after = _apply_commands(before, commands, allocate_gid=lambda: "preview-gid"); preview = _preview_data(version_gid, before, after, commands, expected_revision, _text(payload, "idempotency_key")); repository.put_preview(preview)
    return CapabilityOutput(data={k: v for k, v in preview.items() if k != "expires_at_epoch"}, evidence=(EvidenceRef(kind="craft.bop.preview", reference=f"craft://bop/preview/{preview['preview_gid']}", digest=preview["after_hash"]),))
def apply_draft_change(payload, context):
    preview_gid = _text(payload, "preview_gid", required=True); idempotency_key = _text(payload, "idempotency_key")
    if idempotency_key:
        applied = repository.get_applied(idempotency_key)
        if applied is not None: return CapabilityOutput(data=applied)
    preview = repository.get_preview(preview_gid)
    if not preview: raise CapabilityBusinessError("preview_not_found", "BOP change preview not found")
    if preview.get("expires_at_epoch", 0) <= _now(): raise CapabilityBusinessError("preview_expired", "BOP change preview has expired")
    version = repository.get_version(preview["version_gid"])
    if not version: raise CapabilityBusinessError("bop_version_not_found", "BOP version not found")
    if _revision(version.get("revision")) != preview["base_revision"]: raise CapabilityBusinessError("revision_conflict", "BOP revision changed after preview")
    if not repository.consume_confirmation(preview_gid, context.user_gid, context.confirmation_token or ""): raise CapabilityBusinessError("confirmation_required", "One-time confirmation is required")
    before_hash = _state_hash(version); after = _apply_commands(version, preview["commands"], allocate_gid=next_gid); saved = repository.save_version(after, expected_revision=preview["base_revision"]); result = {"version_gid": saved["gid"], "revision": saved["revision"], "before_hash": before_hash, "after_hash": _state_hash(saved), "preview_gid": preview_gid, "idempotency_key": idempotency_key}
    if idempotency_key: repository.put_applied(idempotency_key, result)
    repository.mark_applied(preview_gid, result); return CapabilityOutput(data=result, evidence=(EvidenceRef(kind="craft.bop.version", reference=f"craft://bop/version/{saved['gid']}", digest=result["after_hash"]),))
def create_bop_version(payload, _context):
    source = _text(payload, "source", required=True)
    if source not in _SOURCE_KINDS: raise ValueError(f"unsupported source: {source}")
    version_tag = _text(payload, "version_tag", required=True); source_version = None
    if source == "bop_version": source_version = repository.get_version(_text(payload, "source_gid", required=True))
    elif source == "template": source_version = repository.get_version(_text(payload, "template_gid", required=True))
    elif source == "import_preview": source_version = getattr(repository, "imports", {}).get(_text(payload, "import_preview_gid", required=True))
    if source != "empty" and source_version is None: raise CapabilityBusinessError("source_not_found", "Creation source not found")
    source_version = source_version or {"entries": [], "links": [], "meta": {}}; version_gid = str(next_gid()); version = copy.deepcopy(source_version); version.update({"gid": version_gid, "version_tag": version_tag, "status": "active", "revision": 1, "parent_version_gid": source_version.get("gid"), "version_family_gid": _text(payload, "version_family_gid") or version_gid}); version["entries"] = [dict(item, gid=str(next_gid())) for item in version.get("entries", [])]; version["links"] = []; created = repository.create_version(version)
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
def import_preview(payload, _context):
    document = payload.get("document")
    if not isinstance(document, dict): raise ValueError("document must be an object")
    entries = document.get("entries", [])
    if not isinstance(entries, list): raise ValueError("document.entries must be an array")
    normalized = {"version_tag": document.get("version_tag"), "bop_name": document.get("bop_name"), "entries": copy.deepcopy(entries)}; digest = content_hash(normalized); preview = {"import_preview_gid": str(next_gid()), "content_hash": digest, "entry_count": len(entries), "document": normalized, "expires_at": _iso(_now() + _TTL_SECONDS)}
    if hasattr(repository, "imports"): repository.imports[preview["import_preview_gid"]] = copy.deepcopy(preview)
    else: repository.put_import_preview(preview)
    return CapabilityOutput(data={k: v for k, v in preview.items() if k != "document"}, evidence=(EvidenceRef(kind="craft.bop.import", reference=f"craft://bop/import/{preview['import_preview_gid']}", digest=digest),))
def register_bop_write_capabilities(registry):
    common = {"owner": "craft", "plugin_callable": False, "permissions": ("craft.write",), "tags": ("craft", "bop", "write")}
    registry.register(CapabilitySpec(id="craft.bop.draft.change.preview", description="Preview a typed BOP draft change without side effects.", risk="read", input_schema={"type": "object", "required": ["version_gid", "expected_revision", "commands"]}, output_schema={"type": "object", "required": ["preview_gid", "version_gid", "base_revision", "before_hash", "after_hash", "expires_at"]}, **common), preview_draft_change)
    registry.register(CapabilitySpec(id="craft.bop.draft.change.apply", description="Apply one exact typed BOP draft preview atomically.", risk="write", confirmation="user", idempotent=True, input_schema={"type": "object", "required": ["preview_gid"]}, output_schema={"type": "object", "required": ["version_gid", "revision", "before_hash", "after_hash"]}, **common), apply_draft_change)
    registry.register(CapabilitySpec(id="craft.bop.version.create", description="Create a BOP draft from an empty, version, template or import preview source.", risk="write", confirmation="user", idempotent=False, input_schema={"type": "object", "required": ["source", "version_tag"]}, output_schema={"type": "object", "required": ["version_gid", "status", "revision", "entries_count"]}, **common), create_bop_version)
    registry.register(CapabilitySpec(id="craft.bop.version.archive", description="Archive a BOP version without deleting its snapshot or references.", risk="write", confirmation="user", idempotent=True, input_schema={"type": "object", "required": ["version_gid", "expected_revision"]}, output_schema={"type": "object", "required": ["version_gid", "status", "revision", "before_hash", "after_hash"]}, **common), archive_bop_version)
    registry.register(CapabilitySpec(id="craft.bop.import.preview", description="Parse and hash a BOP import document without mutating Craft state.", risk="read", input_schema={"type": "object", "required": ["document"]}, output_schema={"type": "object", "required": ["import_preview_gid", "content_hash", "entry_count", "expires_at"]}, **common), import_preview)
