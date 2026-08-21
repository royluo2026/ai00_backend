# Consumer exposure

| Domain | Capability | Enabled consumers |
|---|---|---|

| Agent | `agent.audit.read` | rest |
| Agent | `agent.audit.record` | rest |
| Agent | `agent.flow.change.apply` | rest |
| Agent | `agent.flow.read` | rest |
| Agent | `agent.interaction.cancel` | none |
| Agent | `agent.interaction.chat.change.apply` | none |
| Agent | `agent.interaction.request` | agent |
| Agent | `agent.memory.change.apply` | agent |
| Agent | `agent.memory.read` | agent |
| Agent | `agent.run.change.apply` | rest, agent |
| Agent | `agent.run.read` | agent |
| Agent | `agent.runtime.config.read` | none |
| Agent | `agent.script.generate` | none |
| Agent | `agent.session.change.apply` | rest, agent |
| Agent | `agent.session.read` | rest, agent |
| Agent | `agent.skill.change.apply` | rest |
| Agent | `agent.skill.read` | rest |
| Agent | `agent.tool_catalog.read` | none |
| Base Platform | `base.annotation.change.apply` | rest |
| Base Platform | `base.annotation.read` | rest |
| Base Platform | `base.authorization.grant.change.apply` | rest |
| Base Platform | `base.authorization.grant.read` | rest |
| Base Platform | `base.export_template.change.apply` | rest |
| Base Platform | `base.export_template.read` | rest |
| Base Platform | `base.identity.directory.sync` | rest |
| Base Platform | `base.identity.role.assign` | rest |
| Base Platform | `base.identity.session.get` | rest |
| Base Platform | `base.plugin.marketplace.publisher.register` | rest |
| Base Platform | `base.plugin.marketplace.release.change.apply` | rest |
| Base Platform | `base.plugin.marketplace.search` | rest |
| Base Platform | `base.saved_view.change.apply` | rest |
| Base Platform | `base.saved_view.read` | rest |
| Base Platform | `base.team.change.apply` | rest |
| Base Platform | `base.team.membership.change.apply` | rest |
| Base Platform | `base.team.read` | rest |
| Base Platform | `identity.principal.search` | rest |
| Base Platform | `plugin.disable` | none |
| Base Platform | `plugin.enable` | none |
| Base Platform | `plugin.install` | none |
| Base Platform | `plugin.revoke` | none |
| Base Platform | `plugin.rollback` | none |
| Base Platform | `plugin.storage.delete` | none |
| Base Platform | `plugin.storage.get` | none |
| Base Platform | `plugin.storage.list` | none |
| Base Platform | `plugin.storage.put` | none |
| Base Platform | `plugin.uninstall` | none |
| Base Platform | `plugin.upgrade` | none |
| Base Platform | `semantic.context.get` | none |
| Base Platform | `system.activity.search` | none |
| Base Platform | `system.change_impact.preview` | none |
| Base Platform | `system.job.cancel` | none |
| Base Platform | `system.job.get` | none |
| Base Platform | `system.lineage.get` | none |
| Base Platform | `system.search` | agent |
| Craft | `craft.bop.alt_hierarchy.read` | web, rest |
| Craft | `craft.bop.draft.change.apply` | rest |
| Craft | `craft.bop.draft.change.preview` | rest, agent |
| Craft | `craft.bop.entry.bulk.change.apply` | none |
| Craft | `craft.bop.entry.change.apply` | none |
| Craft | `craft.bop.entry.detail.get` | none |
| Craft | `craft.bop.entry.legacy_read` | web, rest |
| Craft | `craft.bop.entry.search` | web, rest |
| Craft | `craft.bop.entry_link.change.apply` | none |
| Craft | `craft.bop.execution_structure.get` | rest, agent |
| Craft | `craft.bop.execution_structure.preview` | none |
| Craft | `craft.bop.fork.change.apply` | none |
| Craft | `craft.bop.fork_preset.change.apply` | web, rest |
| Craft | `craft.bop.fork_preset.read` | web, rest |
| Craft | `craft.bop.gbop.change.apply` | none |
| Craft | `craft.bop.gbop.legacy_read` | web, rest |
| Craft | `craft.bop.import.preview` | rest |
| Craft | `craft.bop.lifecycle.change.apply` | web, rest |
| Craft | `craft.bop.lifecycle.checkpoint.change.apply` | none |
| Craft | `craft.bop.lifecycle.checkpoint.rollback.apply` | none |
| Craft | `craft.bop.lifecycle.history.change.apply` | none |
| Craft | `craft.bop.lifecycle.read` | web, rest |
| Craft | `craft.bop.lifecycle.state.change.apply` | none |
| Craft | `craft.bop.lifecycle.state.read` | web, rest |
| Craft | `craft.bop.lifecycle.stats.refresh.apply` | none |
| Craft | `craft.bop.lifecycle.step.rollback.apply` | none |
| Craft | `craft.bop.line_operation_catia.read` | web, rest |
| Craft | `craft.bop.linked_parts.get` | rest |
| Craft | `craft.bop.pbom.change_point.get` | web, rest |
| Craft | `craft.bop.pbom_lifecycle.read` | web, rest |
| Craft | `craft.bop.picture.upload` | none |
| Craft | `craft.bop.staging.change.apply` | none |
| Craft | `craft.bop.staging.lifecycle.change.apply` | none |
| Craft | `craft.bop.staging.read` | web, rest |
| Craft | `craft.bop.structure.outline.get` | none |
| Craft | `craft.bop.template.change.apply` | none |
| Craft | `craft.bop.validation.get` | none |
| Craft | `craft.bop.validation.run` | none |
| Craft | `craft.bop.version.archive` | rest |
| Craft | `craft.bop.version.compare` | none |
| Craft | `craft.bop.version.create` | rest |
| Craft | `craft.bop.version.freeze.change.apply` | none |
| Craft | `craft.bop.version.get` | rest |
| Craft | `craft.bop.version.layout.change.apply` | none |
| Craft | `craft.bop.version.legacy_read` | web, rest |
| Craft | `craft.bop.version.lifecycle.change.apply` | web, rest |
| Craft | `craft.bop.version.list` | none |
| Craft | `craft.bop.version.snapshot.change.apply` | none |
| Craft | `craft.bop.work_package.get` | rest |
| Craft | `craft.canvas.change.apply` | rest, agent |
| Craft | `craft.canvas.read` | rest, agent |
| Craft | `craft.data_exchange.export` | rest |
| Craft | `craft.data_exchange.lark.read` | none |
| Craft | `craft.data_exchange.lark.write` | none |
| Craft | `craft.ebom.change.apply` | rest |
| Craft | `craft.ebom.legacy_read` | web, rest |
| Craft | `craft.ebom.read` | rest |
| Craft | `craft.ebom.vpps_check.read` | web, rest |
| Craft | `craft.gbop.catalog.read` | web, rest |
| Craft | `craft.gbop.change.apply` | rest |
| Craft | `craft.gbop.draft.change.apply` | none |
| Craft | `craft.gbop.draft.change.preview` | none |
| Craft | `craft.gbop.draft.create` | none |
| Craft | `craft.gbop.draft.get` | none |
| Craft | `craft.gbop.draft.search` | none |
| Craft | `craft.gbop.draft.submit` | none |
| Craft | `craft.gbop.entity.change.apply` | none |
| Craft | `craft.gbop.import.change.apply` | none |
| Craft | `craft.gbop.import.tc.change.apply` | none |
| Craft | `craft.gbop.item.knowledge.list` | none |
| Craft | `craft.gbop.item.search` | none |
| Craft | `craft.gbop.item.usage.get` | none |
| Craft | `craft.gbop.navigation.change.apply` | web, rest |
| Craft | `craft.gbop.navigation.read` | web, rest |
| Craft | `craft.gbop.process_hierarchy.read` | web, rest |
| Craft | `craft.gbop.read` | rest |
| Craft | `craft.gbop.release.activate` | none |
| Craft | `craft.gbop.release.archive` | none |
| Craft | `craft.gbop.release.compare` | none |
| Craft | `craft.gbop.release.get` | none |
| Craft | `craft.gbop.release.publish` | none |
| Craft | `craft.gbop.release.search` | none |
| Craft | `craft.gbop.station_autolink.change.apply` | none |
| Craft | `craft.gbop.station_autolink.preview` | web, rest |
| Craft | `craft.gbop.version.change.apply` | none |
| Craft | `craft.library.change.apply` | web, rest |
| Craft | `craft.library.read` | web, rest |
| Craft | `craft.manufacturing_resource.change.apply` | rest |
| Craft | `craft.manufacturing_resource.read` | rest |
| Craft | `craft.pbom.draft.change.apply` | none |
| Craft | `craft.pbom.draft.change.preview` | none |
| Craft | `craft.pbom.import.preview` | none |
| Craft | `craft.pbom.part.search` | rest |
| Craft | `craft.pbom.version.archive` | none |
| Craft | `craft.pbom.version.compare` | none |
| Craft | `craft.pbom.version.create` | none |
| Craft | `craft.pbom.version.get` | rest |
| Craft | `craft.pbom.version.publish` | none |
| Craft | `craft.pbom.version.search` | rest |
| Craft | `craft.pbom.version.submit` | none |
| Craft | `craft.rule.change.apply` | rest |
| Craft | `craft.rule.draft.create` | none |
| Craft | `craft.rule.draft.get` | none |
| Craft | `craft.rule.draft.revise` | none |
| Craft | `craft.rule.draft.search` | none |
| Craft | `craft.rule.draft.submit` | none |
| Craft | `craft.rule.engine.evaluate` | web, rest |
| Craft | `craft.rule.evaluate` | none |
| Craft | `craft.rule.library.change.apply` | web, rest |
| Craft | `craft.rule.library.read` | web, rest |
| Craft | `craft.rule.read` | rest, agent |
| Craft | `craft.rule.release.activate` | none |
| Craft | `craft.rule.release.get` | none |
| Craft | `craft.rule.release.publish` | none |
| Craft | `craft.rule.release.search` | none |
| Craft | `craft.rule.waiver.create` | none |
| Craft | `craft.rule.waiver.revoke` | none |
| Craft | `craft.rule.waiver.search` | none |
| Craft | `craft.standard_operation.change.apply` | web, rest |
| Craft | `craft.standard_operation.read` | web, rest |
| Craft | `craft.vpps_audit.change.apply` | web, rest |
| Craft | `craft.vpps_audit.read` | web, rest |
| Device | `local.command.get` | none |
| Device | `local.device.change.apply` | rest |
| Device | `local.device.read` | rest |
| Device | `vismockup.capture` | none |
| Device | `vismockup.highlight` | none |
| Device | `vismockup.launch` | agent, local_runtime |
| Device | `vismockup.model.open` | none |
| Device | `vismockup.status` | none |
| Device | `vismockup.tree` | none |
| Device | `vismockup.visibility` | none |
| Digital Model | `digital_model.component.search` | none |
| Digital Model | `digital_model.model.create` | none |
| Digital Model | `digital_model.model.get` | none |
| Digital Model | `digital_model.model.search` | none |
| Digital Model | `digital_model.version.compare` | none |
| Digital Model | `digital_model.version.create` | none |
| Digital Model | `digital_model.version.get` | none |
| Digital Model | `digital_model.version.search` | none |
| Factory | `factory.asset.get` | none |
| Factory | `factory.asset.maintenance.complete` | none |
| Factory | `factory.asset.maintenance.start` | none |
| Factory | `factory.asset.register` | none |
| Factory | `factory.asset.scrap` | none |
| Factory | `factory.asset.search` | none |
| Factory | `factory.asset.update` | none |
| Factory | `factory.resource.read` | none |
| Factory | `factory.resource_catalog.create` | none |
| Factory | `factory.resource_catalog.deprecate` | none |
| Factory | `factory.resource_catalog.get` | none |
| Factory | `factory.resource_catalog.publish` | none |
| Factory | `factory.resource_catalog.revise` | none |
| Factory | `factory.resource_catalog.search` | none |
| Factory | `factory.structure.archive` | none |
| Factory | `factory.structure.create` | none |
| Factory | `factory.structure.get` | none |
| Factory | `factory.structure.search` | none |
| Factory | `factory.structure.update` | none |
| Integration | `integration.connector.archive` | none |
| Integration | `integration.connector.connection.test` | none |
| Integration | `integration.connector.create` | none |
| Integration | `integration.connector.schema.discover` | none |
| Integration | `integration.connector.search` | none |
| Integration | `integration.connector.update` | none |
| Integration | `integration.mapping.archive` | none |
| Integration | `integration.mapping.create` | none |
| Integration | `integration.mapping.get` | none |
| Integration | `integration.mapping.preview` | none |
| Integration | `integration.mapping.search` | none |
| Integration | `integration.mapping.update` | none |
| Integration | `integration.sync.start` | none |
| Knowledge | `knowledge.context.retrieve` | rest, agent |
| Knowledge | `knowledge.document.acl.grant` | none |
| Knowledge | `knowledge.document.acl.list` | none |
| Knowledge | `knowledge.document.acl.revoke` | none |
| Knowledge | `knowledge.document.archive` | none |
| Knowledge | `knowledge.document.create` | rest |
| Knowledge | `knowledge.document.diff` | none |
| Knowledge | `knowledge.document.get` | rest, agent |
| Knowledge | `knowledge.document.history.get` | rest |
| Knowledge | `knowledge.document.restore` | none |
| Knowledge | `knowledge.document.revise` | rest |
| Knowledge | `knowledge.document.revisions` | none |
| Knowledge | `knowledge.document.rollback` | none |
| Knowledge | `knowledge.document.search` | none |
| Knowledge | `knowledge.entry.change.apply` | none |
| Knowledge | `knowledge.get` | rest, agent |
| Knowledge | `knowledge.hub.change.apply` | web, rest |
| Knowledge | `knowledge.hub.read` | web, rest |
| Knowledge | `knowledge.migration.status` | none |
| Knowledge | `knowledge.personalization.change.apply` | none |
| Knowledge | `knowledge.personalization.read` | none |
| Knowledge | `knowledge.proposal.get` | none |
| Knowledge | `knowledge.proposal.list` | none |
| Knowledge | `knowledge.proposal.outbox.list` | none |
| Knowledge | `knowledge.proposal.outbox.retry` | none |
| Knowledge | `knowledge.proposal.review` | none |
| Knowledge | `knowledge.propose` | none |
| Knowledge | `knowledge.reference_data.change.apply` | none |
| Knowledge | `knowledge.reference_data.read` | none |
| Knowledge | `knowledge.search` | rest, agent |
| Knowledge | `knowledge.space.change.apply` | none |
| Knowledge | `knowledge.space.create` | rest |
| Knowledge | `knowledge.space.list` | rest |
| Knowledge | `knowledge.space.search` | none |
| Ontology | `ontology.change.proposal.create` | none |
| Ontology | `ontology.change.proposal.get` | none |
| Ontology | `ontology.change.proposal.review.submit` | none |
| Ontology | `ontology.change.proposal.search` | none |
| Ontology | `ontology.concept.get` | rest |
| Ontology | `ontology.concept.resolve` | rest, agent |
| Ontology | `ontology.mapping.assess` | rest |
| Ontology | `ontology.mapping.change.apply` | rest |
| Ontology | `ontology.release.activate` | none |
| Ontology | `ontology.release.diff` | rest |
| Ontology | `ontology.release.get` | none |
| Ontology | `ontology.release.publish` | none |
| Ontology | `ontology.release.search` | none |
| Ontology | `ontology.schema.change.apply` | rest |
| Project Management | `base.project.search` | rest, agent |
| Project Management | `project.activity.aggregate` | agent |
| Project Management | `project.approval.change.apply` | rest, agent |
| Project Management | `project.approval.read` | rest, agent |
| Project Management | `project.bitable_binding.change.apply` | none |
| Project Management | `project.bitable_binding.read` | none |
| Project Management | `project.change_log.read` | rest |
| Project Management | `project.collaboration.change.apply` | rest |
| Project Management | `project.collaboration.read` | rest |
| Project Management | `project.craft_scope.read` | rest |
| Project Management | `project.follow.change.apply` | rest |
| Project Management | `project.follow.read` | rest |
| Project Management | `project.issue.change.apply` | rest, agent |
| Project Management | `project.issue.read` | rest, agent |
| Project Management | `project.list.change.apply` | rest |
| Project Management | `project.list.read` | rest |
| Project Management | `project.member.change.apply` | rest |
| Project Management | `project.member.read` | rest |
| Project Management | `project.notification.change.apply` | web, rest |
| Project Management | `project.notification.read` | web, rest |
| Project Management | `project.permission_request.change.apply` | rest |
| Project Management | `project.permission_request.read` | rest |
| Project Management | `project.project.change.apply` | rest |
| Project Management | `project.project.read` | rest |
| Project Management | `project.sharing.change.apply` | rest |
| Project Management | `project.sharing.read` | rest |
| Project Management | `project.task.change.apply` | rest, agent |
| Project Management | `project.task.read` | rest, agent |
| Project Management | `project.task_template.change.apply` | rest |
| Project Management | `project.task_template.read` | rest |
| Project Management | `project.workbench.change.apply` | rest |
| Project Management | `project.workbench.read` | rest |
| Simulation | `simulation.environment.archive` | none |
| Simulation | `simulation.environment.create` | none |
| Simulation | `simulation.environment.get` | none |
| Simulation | `simulation.environment.search` | rest |
| Simulation | `simulation.parameter_set.create` | none |
| Simulation | `simulation.parameter_set.get` | none |
| Simulation | `simulation.parameter_set.search` | none |
| Simulation | `simulation.result.compare` | none |
| Simulation | `simulation.result.get` | none |
| Simulation | `simulation.run.get` | none |
| Simulation | `simulation.run.search` | none |
| Simulation | `simulation.run.start` | none |
| Simulation | `simulation.solver_profile.create` | none |
| Simulation | `simulation.solver_profile.get` | none |
| Simulation | `simulation.solver_profile.search` | none |
