from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityBusinessError

from ..infrastructure import KnowledgeRepository


class KnowledgeOutcomes:
    def __init__(self, repository=None): self.repository = repository or KnowledgeRepository()

    def invoke(self, capability_id, payload, context):
        operation = payload.get("operation"); args = payload.get("arguments") or {}
        user_gid = context.user_gid; tenant_gid = context.team_gid
        repo = self.repository
        if capability_id == "knowledge.entry.change.apply":
            if operation == "entries.create": return repo.entry_create(args, user_gid, tenant_gid)
            if operation == "entries.update": return {"changed": repo.entry_update(args["gid"], args.get("updates", {}), user_gid)}
            if operation == "entries.delete": return {"deleted": repo.entry_delete(args["gid"], user_gid)}
        elif capability_id == "knowledge.space.change.apply":
            if operation == "spaces.update": return {"changed": repo.space_update(args["gid"], args.get("updates", {}), tenant_gid, user_gid)}
            if operation == "spaces.archive": return {"archived": repo.space_archive(args["gid"], tenant_gid, user_gid)}
        elif capability_id == "knowledge.document.archive" and operation == "documents.archive":
            return {"archived": repo.document_archive(args["gid"], tenant_gid, user_gid)}
        elif capability_id == "knowledge.personalization.change.apply":
            if operation == "favorites.toggle": return repo.favorite_toggle(args["gid"], user_gid)
            if operation == "recent.record": return repo.recent_record(args["gid"], user_gid)
        elif capability_id == "knowledge.personalization.read":
            if operation in {"favorites.list", "recent.list"}: return {"items": repo.personalization_read(operation.split(".")[0], user_gid)}
        raise CapabilityBusinessError("invalid_input", f"Unsupported Knowledge operation: {operation}")


knowledge_outcomes = KnowledgeOutcomes()

