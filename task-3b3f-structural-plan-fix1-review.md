PASS — APPROVE

- Project owner is `plugins.project_management.project_management_backend.application.service.ProjectManagementApplication`; its bound source exists at `plugins/project_management/project_management_backend/application/service.py` and the plan owner domain is `project_management`.
- Checker requires and verifies the reviewed source path (`backend/scripts/check_structural_remediation_plan.py:24,125-126,310-316`); missing and substituted Craft paths fail closed in `backend/tests/test_structural_remediation_plan.py:50-75`.
- `python backend/scripts/check_structural_remediation_plan.py --check`: 37 groups / 45 occurrences.
- Focused validator tests: 5 passed. JSON and generated Markdown are current; diff is only report/checker/test/plan JSON/MD, with no frontend or canonical-inventory/BFF/route/catalog/permission/production change.
