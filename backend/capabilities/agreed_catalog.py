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

_COMPLETION_V2_APPROVED = frozenset({
    "craft.bop.validation.get", "craft.bop.validation.run",
    "craft.gbop.draft.change.apply", "craft.gbop.draft.change.preview",
    "craft.gbop.draft.create", "craft.gbop.draft.get", "craft.gbop.draft.search",
    "craft.gbop.draft.submit", "craft.gbop.release.activate", "craft.gbop.release.archive",
    "craft.gbop.release.compare", "craft.gbop.release.get", "craft.gbop.release.publish",
    "craft.gbop.release.search", "craft.pbom.draft.change.apply",
    "craft.pbom.draft.change.preview", "craft.pbom.import.preview",
    "craft.pbom.version.archive", "craft.pbom.version.compare", "craft.pbom.version.create",
    "craft.pbom.version.get", "craft.pbom.version.publish", "craft.pbom.version.search",
    "craft.pbom.version.submit", "craft.rule.draft.create", "craft.rule.draft.get",
    "craft.rule.draft.revise", "craft.rule.draft.search", "craft.rule.draft.submit",
    "craft.rule.evaluate", "craft.rule.release.activate", "craft.rule.release.get",
    "craft.rule.release.publish", "craft.rule.release.search", "craft.rule.waiver.create",
    "craft.rule.waiver.revoke", "craft.rule.waiver.search", "factory.asset.get",
    "factory.asset.maintenance.complete", "factory.asset.maintenance.start",
    "factory.asset.register", "factory.asset.scrap", "factory.asset.search",
    "factory.asset.update", "factory.resource.read", "factory.resource_catalog.create",
    "factory.resource_catalog.deprecate", "factory.resource_catalog.get",
    "factory.resource_catalog.publish", "factory.resource_catalog.revise",
    "factory.resource_catalog.search", "factory.structure.archive", "factory.structure.create",
    "factory.structure.get", "factory.structure.search", "factory.structure.update",
    "knowledge.document.archive", "knowledge.entry.change.apply",
    "knowledge.personalization.change.apply", "knowledge.personalization.read",
    "knowledge.reference_data.change.apply", "knowledge.reference_data.read",
    "knowledge.reference_dataset.publish",
    "knowledge.space.change.apply", "ontology.mapping.change.apply",
    "ontology.schema.change.apply",
})

_FINAL_REVIEWED_APPROVED = frozenset({
    "craft.canvas.change.apply", "craft.canvas.read",
    "craft.data_exchange.export",
    "craft.ebom.change.apply", "craft.ebom.read",
    "craft.gbop.change.apply", "craft.gbop.read",
    "craft.manufacturing_resource.change.apply", "craft.manufacturing_resource.read",
    "craft.rule.change.apply", "craft.rule.read",
    "local.device.change.apply", "local.device.read",
})

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
    "ontology.mapping.assess", "ontology.object.list", "ontology.release.activate", "ontology.release.diff",
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
    "craft.bop.entry.detail.get", "craft.bop.structure.outline.get",
    "craft.bop.version.list", "craft.bop.work_package.get", "craft.gbop.item.knowledge.list",
    "craft.gbop.item.search", "craft.gbop.item.usage.get", "craft.pbom.part.search",
    "craft.bop.draft.change.preview", "craft.bop.draft.change.apply", "craft.bop.version.create", "craft.bop.version.archive", "craft.bop.import.preview",
    "digital_model.model.create", "digital_model.model.get", "digital_model.model.search",
    "digital_model.version.create", "digital_model.version.get", "digital_model.version.search", "digital_model.version.compare",
    "digital_model.component.search",
    "simulation.parameter_set.create", "simulation.parameter_set.get", "simulation.parameter_set.search",
    "simulation.solver_profile.create", "simulation.solver_profile.get", "simulation.solver_profile.search",
    "simulation.environment.create", "simulation.environment.get", "simulation.environment.search", "simulation.environment.archive",
    "simulation.run.start", "simulation.run.get", "simulation.run.search",
    "simulation.result.get", "simulation.result.compare",
    "integration.connector.archive", "integration.connector.connection.test",
    "integration.connector.create", "integration.connector.schema.discover",
    "integration.connector.search", "integration.connector.update",
    "integration.mapping.archive", "integration.mapping.create", "integration.mapping.get",
    "integration.mapping.preview", "integration.mapping.search", "integration.mapping.update",
    "integration.sync.start",
    "agent.audit.read", "agent.audit.record", "agent.flow.change.apply", "agent.flow.read",
    "agent.interaction.request", "agent.memory.change.apply", "agent.memory.read",
    "agent.run.change.apply", "agent.run.read", "agent.session.change.apply", "agent.session.read",
    "agent.skill.change.apply", "agent.skill.read",
}) | _BASE_V2_APPROVED | _PROJECT_V2_APPROVED | _COMPLETION_V2_APPROVED | _FINAL_REVIEWED_APPROVED
