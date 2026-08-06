"""Frozen approved Capability identifiers for the first governed consumer wave."""

FORBIDDEN_INTERNAL_PROTOCOL_IDS = frozenset({
    "system.confirmation.respond", "database.sql.execute", "ois.object.get_bytes",
    "capability.find", "plugin.host.execute", "ontology.graph.query",
})

AGREED_WAVE_PREFIXES = ("craft.", "ontology.", "semantic.", "identity.", "base.", "system.search", "system.activity", "system.job", "system.lineage", "system.change_impact", "knowledge.context", "knowledge.document", "knowledge.space")

APPROVED_CAPABILITY_IDS = frozenset({
    "base.project.search", "identity.principal.search", "knowledge.context.retrieve",
    "knowledge.document.create", "knowledge.document.diff", "knowledge.document.get",
    "knowledge.document.history.get", "knowledge.document.restore", "knowledge.document.revise",
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
    "plugin.uninstall", "plugin.upgrade", "plugin.upgrade.finish", "semantic.context.get",
    "system.activity.search", "system.change_impact.preview", "system.echo", "system.job.cancel",
    "system.job.get", "system.lineage.get", "system.search", "system.worker.outbox.health",
    "vismockup.capture", "vismockup.highlight", "vismockup.launch", "vismockup.open_file",
    "vismockup.status", "vismockup.tree", "vismockup.visibility",
    "craft.bop.execution_structure.get", "craft.bop.execution_structure.preview",
    "craft.bop.linked_parts.get", "craft.bop.version.compare", "craft.bop.version.get",
    "craft.bop.version.list", "craft.bop.work_package.get", "craft.gbop.item.knowledge.list",
    "craft.gbop.item.search", "craft.gbop.item.usage.get", "craft.pbom.part.search",
    "craft.pbom.snapshot.compare", "craft.pbom.snapshot.get",
})
