from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityBusinessError

from ..infrastructure import KnowledgeRepository


class KnowledgeOutcomes:
    def __init__(self, repository=None): self.repository = repository or KnowledgeRepository()

    def invoke(self, capability_id, payload, context):
        operation = payload.get("operation"); args = payload.get("arguments") or {}
        user_gid = context.user_gid; tenant_gid = context.team_gid
        repo = self.repository
        permissions = tuple(getattr(context, "permissions", ()) or ())
        active_roles = tuple(getattr(context, "active_roles", ()) or ())
        if capability_id == "knowledge.entry.change.apply":
            if operation == "entries.create": return repo.entry_create(args, user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)
            if operation == "entries.update": return {"changed": repo.entry_update(args["gid"], args.get("updates", {}), user_gid, permissions=permissions, active_roles=active_roles)}
            if operation == "entries.delete": return {"deleted": repo.entry_delete(args["gid"], user_gid, permissions=permissions, active_roles=active_roles)}
        elif capability_id == "knowledge.space.change.apply":
            if operation == "spaces.update": return {"changed": repo.space_update(args["gid"], args.get("updates", {}), tenant_gid, user_gid)}
            if operation == "spaces.archive": return {"archived": repo.space_archive(args["gid"], tenant_gid, user_gid)}
        elif capability_id == "knowledge.document.archive" and operation == "documents.archive":
            return {"archived": repo.document_archive(args["gid"], tenant_gid, user_gid)}
        elif capability_id == "knowledge.personalization.change.apply":
            if operation == "favorites.toggle": return repo.favorite_toggle(args["gid"], user_gid, tenant_gid)
            if operation == "recent.record": return repo.recent_record(args["gid"], user_gid, tenant_gid)
        elif capability_id == "knowledge.personalization.read":
            if operation in {"favorites.list", "recent.list"}: return {"items": repo.personalization_read(operation.split(".")[0], user_gid, tenant_gid, limit=args.get("limit"))}
        elif capability_id == "knowledge.hub.read":
            if operation == "folders.list": return {"items": repo.folder_list(args, user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)}
            if operation == "items.list": return {"items": repo.item_list(args, user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)}
            if operation == "items.get": return repo.item_get(args["gid"], user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)
            if operation == "items.history.get": return {"items": repo.item_history(args["gid"], user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)}
        elif capability_id == "knowledge.hub.change.apply":
            if operation == "folders.create": return repo.folder_create(args, user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)
            if operation == "folders.update": return {"changed": repo.folder_update(args["gid"], args.get("updates", {}), user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)}
            if operation == "folders.delete": return repo.folder_delete(args["gid"], user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)
            if operation == "items.create": return repo.item_create(args, user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)
            if operation == "items.update": return {"changed": repo.item_update(args["gid"], args.get("updates", {}), user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)}
            if operation == "items.delete": return {"deleted": repo.item_delete(args["gid"], user_gid, tenant_gid, permissions=permissions, active_roles=active_roles)}
        raise CapabilityBusinessError("invalid_input", f"Unsupported Knowledge operation: {operation}")


knowledge_outcomes = KnowledgeOutcomes()
