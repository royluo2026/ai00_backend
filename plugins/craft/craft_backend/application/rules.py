from __future__ import annotations
import hashlib
import json
import uuid
from ..domain.rules import RuleRelease, RuleWaiver
from ..data.connection import get_conn
from ..rule_engine.executor import validate_cel_expression


RULE_DEFINITION_FIELDS = frozenset({
    "name", "description", "severity", "enabled", "condition", "message",
    "scope", "tags", "priority", "category",
})
_RULE_DEFINITION_VALUE_FIELDS = RULE_DEFINITION_FIELDS - {"name", "condition"}
_STRING_LIMITS = {
    "name": 2000, "description": 2000, "severity": 64, "message": 2000,
    "scope": 128, "category": 128,
}


def canonical_rule_definition_command(payload):
    """Hash only the closed command, never browser-supplied implementation metadata."""
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_rule_definition_changes(changes):
    if not isinstance(changes, dict) or not changes or set(changes) - RULE_DEFINITION_FIELDS:
        raise ValueError("unsupported rule definition changes")
    result = dict(changes)
    for key, value in result.items():
        if key in _STRING_LIMITS:
            if not isinstance(value, str) or not value or len(value) > _STRING_LIMITS[key]:
                raise ValueError(f"invalid rule {key}")
        elif key == "enabled":
            if not isinstance(value, bool):
                raise ValueError("invalid rule enabled")
        elif key == "priority":
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
                raise ValueError("invalid rule priority")
        elif key == "tags":
            if not isinstance(value, list) or len(value) > 32 or any(not isinstance(item, str) or not item or len(item) > 128 for item in value):
                raise ValueError("invalid rule tags")
        elif key == "condition":
            if not validate_cel_expression(value):
                raise ValueError("unsafe rule condition")
    return result


def closed_rule_projection(rule):
    definition = rule.get("rule_definition") or {}
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except ValueError:
            definition = {}
    if not isinstance(definition, dict):
        definition = {}
    def text(value, limit): return value if isinstance(value, str) and len(value) <= limit else ""
    def revision(value): return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 2_147_483_647 else 1
    tags = definition.get("tags")
    return {
        "rule_gid": text(rule.get("gid"), 255),
        "revision": revision(rule.get("revision") or definition.get("_revision")),
        "name": text(rule.get("name"), _STRING_LIMITS["name"]),
        "description": text(definition.get("description"), _STRING_LIMITS["description"]),
        "severity": text(definition.get("severity"), _STRING_LIMITS["severity"]),
        "enabled": definition.get("enabled") if isinstance(definition.get("enabled"), bool) else False,
        "condition": rule.get("expression") if validate_cel_expression(rule.get("expression")) else "",
        "message": text(definition.get("message"), _STRING_LIMITS["message"]),
        "scope": text(definition.get("scope"), _STRING_LIMITS["scope"]),
        "tags": [item for item in tags[:32] if isinstance(item, str) and 0 < len(item) <= 128] if isinstance(tags, list) else [],
        "priority": definition.get("priority") if isinstance(definition.get("priority"), int) and not isinstance(definition.get("priority"), bool) and 0 <= definition["priority"] <= 100 else 0,
        "category": text(definition.get("category"), _STRING_LIMITS["category"]),
    }


class RuleDefinitionRepository:
    """Craft-owned transactional rule-definition persistence boundary."""

    def change(self, *, rule_gid, expected_revision, changes, actor_gid, team_gid, idempotency_key, command_digest):
        raise NotImplementedError


class MysqlRuleDefinitionRepository(RuleDefinitionRepository):
    def change(self, *, rule_gid, expected_revision, changes, actor_gid, team_gid, idempotency_key, command_digest):
        with get_conn() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT gid,name,expression,rule_definition,applicable_scope,owner_user_gid,creator_gid "
                        "FROM workmanship_know_craft_rules WHERE gid=%s FOR UPDATE",
                        (rule_gid,),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise LookupError("rule not found")
                    rule = dict(row)
                    definition = rule.get("rule_definition") or {}
                    if isinstance(definition, str):
                        definition = json.loads(definition)
                    scope = rule.get("applicable_scope") or {}
                    if isinstance(scope, str):
                        try:
                            scope = json.loads(scope)
                        except ValueError:
                            scope = {}
                    if not isinstance(scope, dict) or not isinstance(scope.get("team_gid"), str) or not scope["team_gid"] or (rule.get("owner_user_gid") or rule.get("creator_gid")) != actor_gid or scope["team_gid"] != team_gid:
                        raise LookupError("rule not found")
                    cur.execute(
                        "SELECT result_json FROM workmanship_craft_bop_write_idempotency WHERE idempotency_key=%s AND capability_id=%s FOR UPDATE",
                        (idempotency_key, "craft.rule.definition.change.apply"),
                    )
                    replay = cur.fetchone()
                    if replay:
                        stored = json.loads(replay["result_json"]) if isinstance(replay["result_json"], str) else replay["result_json"]
                        if stored.get("actor_gid") != actor_gid or stored.get("team_gid") != team_gid:
                            raise LookupError("rule not found")
                        if stored.get("command_digest") != command_digest or stored.get("rule_gid") != rule_gid:
                            from backend.capability_v2.provider_contracts import CapabilityBusinessError
                            raise CapabilityBusinessError("idempotency_conflict", "The idempotency key is bound to another Craft rule command.")
                        conn.commit()
                        return stored["result"]
                    revision = int(definition.get("_revision") or 1)
                    if revision != expected_revision:
                        from backend.capability_v2.provider_contracts import CapabilityBusinessError
                        raise CapabilityBusinessError("revision_conflict", "The requested rule revision is unavailable.")
                    rule["name"] = changes.get("name", rule.get("name"))
                    rule["expression"] = changes.get("condition", rule.get("expression"))
                    for field in _RULE_DEFINITION_VALUE_FIELDS:
                        if field in changes:
                            definition[field] = changes[field]
                    definition["_revision"] = revision + 1
                    rule["rule_definition"] = definition
                    result = closed_rule_projection(rule)
                    cur.execute(
                        "UPDATE workmanship_know_craft_rules SET name=%s,expression=%s,rule_definition=%s,updated_at=NOW() WHERE gid=%s",
                        (rule["name"], rule["expression"], json.dumps(definition, ensure_ascii=False), rule_gid),
                    )
                    if cur.rowcount != 1:
                        raise LookupError("rule not found")
                    cur.execute(
                        "INSERT INTO workmanship_craft_bop_write_idempotency (idempotency_key,capability_id,version_gid,result_json,created_by) VALUES (%s,%s,%s,%s,%s)",
                        (idempotency_key, "craft.rule.definition.change.apply", rule_gid, json.dumps({"actor_gid": actor_gid, "team_gid": team_gid, "rule_gid": rule_gid, "command_digest": command_digest, "result": result}, ensure_ascii=False), actor_gid),
                    )
                    cur.execute(
                        "INSERT INTO workmanship_app_capability_audit (event_type,capability_id,version,user_gid,source,request_id,payload_hash,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        ("rule_definition_operation", "craft.rule.definition.change.apply", 1, actor_gid, "craft", idempotency_key, command_digest, "completed"),
                    )
                    cur.execute(
                        "INSERT INTO workmanship_app_capability_audit (event_type,capability_id,version,user_gid,source,request_id,payload_hash,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        ("rule_definition_changed", "craft.rule.definition.change.apply", 1, actor_gid, "craft", idempotency_key, command_digest, "succeeded"),
                    )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise


def _definition(rule):
    value = rule.get("rule_definition") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = {}
    return value if isinstance(value, dict) else {}


def rule_revision(rule):
    value = _definition(rule).get("_revision")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else 1


def load_visible_rule(rule_gid, user_gid, team_gid):
    """Load one rule only when the caller can see its owner or team scope."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, owner_user_gid, creator_gid, share_scope, expression, rule_definition, applicable_scope "
                "FROM workmanship_know_craft_rules WHERE gid=%s",
                (rule_gid,),
            )
            row = cur.fetchone()
    if not row:
        raise LookupError("rule not found")
    rule = dict(row)
    scope = rule.get("applicable_scope") or {}
    if isinstance(scope, str):
        try:
            scope = json.loads(scope)
        except ValueError:
            scope = {}
    stored_team_gid = scope.get("team_gid") if isinstance(scope, dict) else None
    stored_team_gid = stored_team_gid or rule.get("team_gid")
    owner_user_gid = rule.get("owner_user_gid") or rule.get("creator_gid")
    if not (
        rule.get("share_scope") == "global"
        or owner_user_gid == user_gid
        or (rule.get("share_scope") == "team" and team_gid and stored_team_gid == team_gid)
    ):
        raise LookupError("rule not found")
    rule["owner_user_gid"] = owner_user_gid
    rule["team_gid"] = stored_team_gid
    return rule

class RuleService:
    def __init__(self, releases=()): self.releases = {r.ref: r for r in releases}; self.waivers = {}
    def get_release(self, ref): return self.releases[ref]
    def waive(self, release_ref, violation, reason):
        self.get_release(release_ref)
        waiver = RuleWaiver(ref=f"craft:rule-waiver:{uuid.uuid4().hex}", release_ref=release_ref, violation=violation, reason=reason)
        self.waivers[waiver.ref] = waiver
        return waiver

__all__ = ["RuleService", "RuleDefinitionRepository", "MysqlRuleDefinitionRepository", "RULE_DEFINITION_FIELDS", "canonical_rule_definition_command", "closed_rule_projection", "load_visible_rule", "rule_revision", "validate_rule_definition_changes"]
