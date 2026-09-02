# Domain Ownership Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make domain ownership, CODEOWNERS coverage, and shared-directory review rules executable and testable for the four-person development split.

**Architecture:** Extend the existing `docs/governance/domain-ownership.json` as the single ownership source, keep exact table ownership in the existing registry by reference, and add one standard-library-only checker that validates manifest completeness and CODEOWNERS coverage. Use repository-native CODEOWNERS files for backend and frontend review routing.

**Tech Stack:** JSON, Python standard library, pytest, Git CODEOWNERS.

**Spec:** Approved in chat and recorded in the Feishu document `总装柔性智能基座协作开发规范V0.1`.

## Global Constraints

- Preserve all existing uncommitted work and do not modify unrelated governance-center implementation files.
- Do not duplicate the exact table registry; reference `backend/governance/domain_table_ownership.json` from the ownership manifest.
- Shared paths require the platform maintainer and explicit affected-domain review policy.
- Do not push or merge.

### Task 1: Define executable ownership rules

**Files:**
- Create: `backend/tests/test_domain_change_governance.py`
- Create: `backend/scripts/check_domain_change_governance.py`

**Interfaces:**
- `validate_ownership(root: Path) -> list[str]`
- CLI exits `0` only when ownership and CODEOWNERS are consistent.

- [ ] Write tests that fail when a domain lacks frontend/capability/table ownership metadata.
- [ ] Write tests that fail when a shared path lacks platform CODEOWNERS coverage.
- [ ] Write tests that fail when an owned path lacks its domain maintainer.
- [ ] Implement the smallest validator that passes the tests.

### Task 2: Complete backend ownership facts

**Files:**
- Modify: `docs/governance/domain-ownership.json`
- Modify: `.github/CODEOWNERS`

- [ ] Add schema metadata for exact table ownership, capability prefixes, frontend source paths, and shared paths.
- [ ] Add CODEOWNERS rules for shared governance and deployed frontend paths.
- [ ] Run the validator and existing domain-independence tests.

### Task 3: Add frontend repository review routing

**Files:**
- Create: `E:/Projects/ai00/workmanship-web/.github/CODEOWNERS`

- [ ] Map domain package/page paths to domain maintainers.
- [ ] Map `web/core`, workspace/workbench/components, plugin SDK, build and governance UI to platform maintainers.
- [ ] Verify the file parses into non-empty path/owner rules.

### Task 4: Document and verify

**Files:**
- Update: Feishu document `总装柔性智能基座协作开发规范V0.1`.

- [ ] Run focused pytest and both ownership checks.
- [ ] Append the implemented file locations, enforcement behavior, and team workflow to Feishu.

