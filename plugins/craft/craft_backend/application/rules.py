from __future__ import annotations
import uuid
from ..domain.rules import RuleRelease, RuleWaiver

class RuleService:
    def __init__(self, releases=()): self.releases = {r.ref: r for r in releases}; self.waivers = {}
    def get_release(self, ref): return self.releases[ref]
    def waive(self, release_ref, violation, reason):
        self.get_release(release_ref)
        waiver = RuleWaiver(ref=f"craft:rule-waiver:{uuid.uuid4().hex}", release_ref=release_ref, violation=violation, reason=reason)
        self.waivers[waiver.ref] = waiver
        return waiver

__all__ = ["RuleService"]
