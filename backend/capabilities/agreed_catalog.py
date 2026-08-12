"""Frozen approved Capability identifiers for the first governed consumer wave."""

FORBIDDEN_INTERNAL_PROTOCOL_IDS = frozenset({
    "system.confirmation.respond", "database.sql.execute", "ois.object.get_bytes",
    "capability.find", "plugin.host.execute", "ontology.graph.query",
})

AGREED_WAVE_PREFIXES = ("craft.", "ontology.", "semantic.", "identity.", "base.", "system.search", "system.activity", "system.job", "system.lineage", "system.change_impact", "knowledge.context", "knowledge.document", "knowledge.space")

_BASE_V2_APPROVED = frozenset(
    "base." + suffix
    for suffix in {
        "annotation.change.apply", "annotation.read",
        "approval.request.cancel", "approval.request.create",
        "approval.request.decide", "approval.request.get", "approval.request.search",
        "authorization.grant.change.apply", "authorization.grant.read",
        "export_template.change.apply", "export_template.read",
        "identity.directory.sync", "identity.role.assign", "identity.session.get",
        "notification.preference.get", "notification.preference.update",
        "notification.read_state.set", "notification.search",
        "plugin.marketplace.publisher.register",
        "plugin.marketplace.release.change.apply", "plugin.marketplace.search",
        "saved_view.change.apply", "saved_view.read", "team.change.apply",
        "team.membership.change.apply", "team.read",
        "workspace.template.publish", "workspace.template.read",
    }
)

_PROJECT_V2_APPROVED = frozenset(
    "project." + suffix
    for suffix in {
        "activity.aggregate", "approval.change.apply", "approval.read",
        "bitable_binding.change.apply", "bitable_binding.read", "change_log.read",
        "collaboration.change.apply", "collaboration.read", "craft_scope.read",
        "follow.change.apply", "follow.read", "issue.change.apply", "issue.read",
        "list.change.apply", "list.read", "member.change.apply", "member.read",
        "notification.change.apply", "notification.read",
        "permission_request.change.apply", "permission_request.read",
        "project.change.apply", "project.read", "sharing.change.apply", "sharing.read",
        "task.change.apply", "task.read", "task_template.change.apply",
        "task_template.read", "workbench.change.apply", "workbench.read",
    }
)

APPROVED_CAPABILITY_IDS = frozenset({
    "base.project.search", "identity.principal.search", "knowledge.context.retrieve",
    "knowledge.document.create", "knowledge.document.diff", "knowledge.document.get",
    "knowledge.document.history.get", "knowledge.document.restore", "knowledge.document.revise", "knowledge.document.search",
    "knowledge.document.acl.list", "knowledge.document.acl.grant", "knowledge.document.acl.revoke",
    "knowledge.document.revisions", "knowledge.document.rollback", "knowledge.get",
    "knowledge.migration.status", "knowledge.proposal.get", "knowledge.proposal.list",
    "knowledge.proposal.outbox.list", "knowledge.proposal.outbox.retry", "knowledge.proposal.review",
    "knowledge.propose", "knowledge.search", "knowledge.space.create", "knowledge.space.list",
    "knowledge.space.search", "local.command.get", "ontology.change.proposal.create",
    "ontology.change.proposal.get", "ontology.change.proposal.review.submit",
    "ontology.change.proposal.search", "ontology.concept.get", "ontology.concept.resolve",
    "ontology.mapping.assess", "ontology.release.activate", "ontology.release.diff",
    "ontology.release.get", "ontology.release.publish", "ontology.release.search",
    "plugin.disable", "plugin.enable", "plugin.install", "plugin.revoke", "plugin.rollback",
    "plugin.storage.delete", "plugin.storage.get", "plugin.storage.list", "plugin.storage.put",
    "plugin.uninstall", "plugin.upgrade", "semantic.context.get",
    "system.activity.search", "system.change_impact.preview", "system.job.cancel",
    "system.job.get", "system.lineage.get", "system.search",
    "vismockup.capture", "vismockup.highlight", "vismockup.launch", "vismockup.model.open",
    "vismockup.status", "vismockup.tree", "vismockup.visibility",
    "craft.bop.execution_structure.get", "craft.bop.execution_structure.preview",
    "craft.bop.linked_parts.get", "craft.bop.version.compare", "craft.bop.version.get",
    "craft.bop.version.list", "craft.bop.work_package.get", "craft.gbop.item.knowledge.list",
    "craft.gbop.item.search", "craft.gbop.item.usage.get", "craft.pbom.part.search",
    "craft.pbom.snapshot.compare", "craft.pbom.snapshot.get", "craft.bop.draft.change.preview", "craft.bop.draft.change.apply", "craft.bop.version.create", "craft.bop.version.archive", "craft.bop.import.preview",
    "digital_model.model.create", "digital_model.model.get", "digital_model.model.search",
    "digital_model.version.create", "digital_model.snapshot.get", "digital_model.snapshot.compare",
    "digital_model.component.search",
    "simulation.parameter_set.create", "simulation.parameter_set.get",
    "simulation.profile.create", "simulation.profile.get",
    "simulation.environment.create", "simulation.environment.get", "simulation.environment.list",
    "simulation.run.start", "simulation.run.get", "simulation.result.get",
}) | _BASE_V2_APPROVED | _PROJECT_V2_APPROVED
