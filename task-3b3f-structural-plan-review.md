REQUEST CHANGES

- [P1] The Project approval group names a nonexistent owner service: `plugins.project.project_backend.application.approval_service` in `backend/scripts/check_structural_remediation_plan.py:124` (rendered at `docs/governance/capability-v2-structural-remediation-plan.json:1243,2525` and `.md:93,351`).
  The real Project package is `plugins/project_management/project_management_backend/application/service.py`, whose `ProjectManagementApplication` owns `approval.orders.reject` (lines 317, 468-494); the prior evidence manifests use that same package path.
  Correct the owner-service contract to the Project Management namespace (and the actual/newly defined approval boundary), then regenerate JSON/Markdown and add a source-namespace regression.
- Otherwise approved: checker `--check` reports 37 groups / 45 occurrences; focused validator suite is 4 passed; duplicate/missing occurrence, owner substitution, and operations/BFF reclassification fail closed.
- Diff is limited to the plan/checker/test/report; no frontend, production, catalog, permission, route, BFF, or canonical inventory change.
