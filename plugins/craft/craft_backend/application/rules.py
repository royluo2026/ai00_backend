from __future__ import annotations
import uuid
from ..domain.rules import RuleRelease, RuleWaiver
from ..data.connection import get_conn


def load_visible_rule(rule_gid, user_gid, team_gid):
    """Load one rule only when the caller can see its owner or team scope."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, owner_user_gid, share_scope, expression, "
                "JSON_UNQUOTE(JSON_EXTRACT(applicable_scope, '$.team_gid')) AS team_gid, "
                "DATE_FORMAT(updated_at, '%Y-%m-%dT%H:%i:%s.%f') AS rule_revision "
                "FROM workmanship_know_craft_rules WHERE gid=%s",
                (rule_gid,),
            )
            row = cur.fetchone()
    if not row:
        raise LookupError("rule not found")
    rule = dict(row)
    if not (
        rule.get("share_scope") == "global"
        or rule.get("owner_user_gid") == user_gid
        or (team_gid and rule.get("team_gid") == team_gid)
    ):
        raise LookupError("rule not found")
    return rule


def rule_revision(rule):
    value = rule.get("rule_revision") or rule.get("updated_at")
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    return str(value or "")

class RuleService:
    def __init__(self, releases=()): self.releases = {r.ref: r for r in releases}; self.waivers = {}
    def get_release(self, ref): return self.releases[ref]
    def waive(self, release_ref, violation, reason):
        self.get_release(release_ref)
        waiver = RuleWaiver(ref=f"craft:rule-waiver:{uuid.uuid4().hex}", release_ref=release_ref, violation=violation, reason=reason)
        self.waivers[waiver.ref] = waiver
        return waiver

__all__ = ["RuleService", "load_visible_rule", "rule_revision"]
