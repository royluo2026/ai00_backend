# Agent Chat Capability V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four Xiaorou chat and confirmation routes pass trusted Capability Gateway authorization and schema validation by migrating them to a parallel `agent.interaction.chat.change.apply@2`, while preserving the published `@1` contract.

**Architecture:** Keep `@1` registered with its frozen strong-consistency, required-evidence, user-confirmation Descriptor. Register `@2` beside it with a closed Web-adapter contract, eventual consistency, optional evidence, and no chat-level confirmation; the Web facade pins major 2 and continues deriving identity and idempotency server-side. Grant `agent.interact` only through trusted internal-user profile projection, then regenerate governance artifacts without fabricating business approval or runtime evidence.

**Tech Stack:** Python 3, FastAPI, Pydantic, pytest, Capability V2.5 Gateway/Catalog tooling, deterministic JSON governance generators.

**Spec:** `docs/superpowers/specs/2026-09-03-agent-chat-v2-design.md`

## Global Constraints

- Preserve `agent.interaction.chat.change.apply@1` as a concurrently registered stable major with business definition hash `sha256:cd4e5f972aeffa4be59487b94163c985098a720c7c09e23825f617d704e13805`.
- Add `agent.interaction.chat.change.apply@2`; do not mutate `@1` to obtain the fix.
- Actor identity comes only from the trusted invocation envelope; remove caller-supplied `user_gid` before Capability validation.
- A supplied session must remain subject to the legacy Agent session ownership checks for the authenticated actor.
- Chat-level confirmation is `none`; confirmation required by invoked write tools remains unchanged.
- Stream output contains at most 500 serialized SSE events. Bound `context_json` to 65,536 characters and synchronous `response_json` to 1,048,576 characters.
- `@2` is a write Capability with `eventual` consistency, `optional` evidence, required Gateway idempotency, `agent.interact`, and confidential data classification.
- The shared compatibility-envelope API defaults to major 1; only the four Agent chat/confirmation routes pin major 2.
- Do not add a database migration or a dependency.
- Do not manufacture `human_approved` or `runtime_verified` evidence. A release remains blocked until the exact generated `capability_version_gid` and `business_definition_hash` are approved through the trusted server workflow and controlled runtime evidence is captured.
- Preserve unrelated working-tree changes and commit only files named by each task.

## File map

- `backend/platform_sdk/effective_identity.py`: canonical effective permission projection for trusted identities.
- `backend/routers/deps.py`: legacy authenticated Web profile projection used by first-party routes.
- `plugins/agent/agent_backend/capabilities/interaction_chat_change.py`: frozen `@1`, corrected `@2`, Provider adapters, and bounded transport conversion.
- `plugins/agent/agent_backend/capabilities/provider.py`: common Agent Descriptor policy; no broad policy change is required.
- `plugins/agent/agent_backend/capabilities/__init__.py`: calls the chat registration function, which will register both majors.
- `plugins/factory/factory_backend/api/compatibility.py`: shared first-party Web envelope implementation re-exported by `backend.platform_sdk.factory`.
- `plugins/agent/agent_backend/routers/ai_chat.py`: Xiaorou Web payload normalization, major pinning, and response rehydration.
- `backend/tests/test_agent_interaction_chat_change_boundary.py`: focused authorization, versioning, Gateway, payload, SSE, JSON, and identity-boundary tests.
- `backend/tests/test_web_compatibility_adapters.py`: regression test for the shared builder's default and explicit major selection.
- `plugins/agent/tests/test_agent_provider.py`: Agent Provider inventory and Descriptor-policy regression tests.
- `docs/governance/legacy_route_inventory.json`: four Agent route bindings updated to major 2.
- `docs/governance/web-api-legacy-addition-review.json`: refreshed source anchors for the four Agent routes.
- `docs/governance/user-function-registry.json`: regenerated route-to-Capability consumer projection.
- `backend/capability_v2/official_domains.json`: regenerated trusted Agent and Factory Provider artifact hashes because the shared envelope implementation is Factory-owned.
- `docs/governance/capability-catalog-release.json` and `docs/governance/capability-catalog-lineage.json`: regenerated Catalog release and lineage containing both majors.
- `backend/tests/acceptance/fixtures/case-manifest.json`: generated seven-case acceptance bindings for `@2` while retaining `@1`.
- `docs/capabilities/catalog.v2.json`, `docs/capabilities/agent-tools.v2.json`, `docs/capabilities/mcp-tools.v2.json`, `docs/capabilities/openapi-fragment.v2.json`, `docs/capabilities/.generated-manifest.json`, and `docs/capabilities/agent/agent.interaction.chat.change.apply@2.md`: regenerated consumer documentation.

---

### Task 1: Project `agent.interact` from trusted internal identities

**Files:**
- Modify: `backend/platform_sdk/effective_identity.py:55-75`
- Modify: `backend/routers/deps.py:330-355`
- Test: `backend/tests/test_agent_interaction_chat_change_boundary.py`

**Interfaces:**
- Consumes: `build_effective_profile(user: dict[str, Any], grants: list[dict[str, Any]]) -> dict[str, Any]` and `deps.build_profile(user: dict) -> dict`.
- Produces: both profile paths include `agent.interact` exactly when `org_role != "external"`.

- [ ] **Step 1: Add failing internal and external identity tests**

```python
@pytest.mark.parametrize(
    ("system_role", "org_role"),
    (("member", "member"), ("super_admin", "super_admin")),
)
def test_internal_user_can_authorize_agent_chat(monkeypatch, system_role, org_role):
    user = {
        "gid": f"{system_role}-1",
        "system_role": system_role,
        "org_role": org_role,
        "is_active": True,
    }
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    assert "agent.interact" in deps.build_profile(user)["permissions"]
    assert "agent.interact" in build_effective_profile(user, [])["permissions"]


def test_external_user_cannot_authorize_agent_chat(monkeypatch):
    user = {
        "gid": "external-1",
        "system_role": "member",
        "org_role": "external",
        "is_active": True,
    }
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])
    assert "agent.interact" not in deps.build_profile(user)["permissions"]
    assert "agent.interact" not in build_effective_profile(user, [])["permissions"]
```

- [ ] **Step 2: Run the focused tests and confirm the missing permission**

Run: `python -m pytest backend/tests/test_agent_interaction_chat_change_boundary.py -k "authorize_agent_chat" -q`

Expected: the two internal cases fail because `agent.interact` is absent; the external case passes.

- [ ] **Step 3: Add the minimal permission projection in both trusted profile builders**

```python
if org_role != "external":
    permissions.add("agent.interact")
```

Use `v2_perms.add(...)` instead of `permissions.add(...)` in `backend/routers/deps.py` to match that function's local variable.

- [ ] **Step 4: Run the identity tests**

Run: `python -m pytest backend/tests/test_agent_interaction_chat_change_boundary.py -k "authorize_agent_chat" -q`

Expected: 3 passed.

- [ ] **Step 5: Commit the authorization fix**

```bash
git add backend/platform_sdk/effective_identity.py backend/routers/deps.py backend/tests/test_agent_interaction_chat_change_boundary.py
git commit -m "fix(agent): grant chat capability to internal users"
```

### Task 2: Register an immutable V1 and corrected V2 Provider contract

**Files:**
- Modify: `plugins/agent/agent_backend/capabilities/interaction_chat_change.py`
- Modify: `plugins/agent/tests/test_agent_provider.py`
- Test: `backend/tests/test_agent_interaction_chat_change_boundary.py`

**Interfaces:**
- Consumes: `CapabilityRegistry.register(spec, handler, descriptor=...)`, `descriptor_for(spec)`, and the legacy `_legacy_chat_stream`, `_legacy_chat_sync`, `_legacy_confirm_tool`, and `_legacy_confirm_tool_sync` callables.
- Produces: `apply_interaction_chat_change_v1(payload, context)`, `apply_interaction_chat_change(payload, context)` for V2, and `register_interaction_chat_change_capability(registry)` registering `(id, 1)` and `(id, 2)`.

- [ ] **Step 1: Add failing version and frozen-contract tests**

```python
from backend.capability_v2.business_definition import business_definition_hash


def test_agent_chat_registers_frozen_v1_and_corrected_v2():
    registry = CapabilityRegistry()
    register_interaction_chat_change_capability(registry)
    v1 = registry.get("agent.interaction.chat.change.apply", 1)
    v2 = registry.get("agent.interaction.chat.change.apply", 2)

    assert business_definition_hash(v1.descriptor) == (
        "sha256:cd4e5f972aeffa4be59487b94163c985098a720c7c09e23825f617d704e13805"
    )
    assert v1.spec.confirmation == "user"
    assert v1.descriptor.consistency_policy == "strong"
    assert v1.descriptor.evidence_policy == "required"
    assert v2.spec.version == 2
    assert v2.spec.confirmation == "none"
    assert v2.descriptor.consistency_policy == "eventual"
    assert v2.descriptor.evidence_policy == "optional"
    assert v2.descriptor.idempotency_policy == "required"
    assert v2.spec.input_schema["properties"]["body"]["additionalProperties"] is False
    assert v2.spec.output_schema["properties"]["data"]["additionalProperties"] is False
```

Update `plugins/agent/tests/test_agent_provider.py` to assert the versioned key set instead of assuming one entry per ID:

```python
chat_versions = {
    spec.version
    for spec, _descriptor in registry.items
    if spec.id == "agent.interaction.chat.change.apply"
}
assert chat_versions == {1, 2}
```

- [ ] **Step 2: Run the Provider contract tests and confirm V2 is missing**

Run: `python -m pytest backend/tests/test_agent_interaction_chat_change_boundary.py::test_agent_chat_registers_frozen_v1_and_corrected_v2 plugins/agent/tests/test_agent_provider.py -q`

Expected: failure because only one mutated major is currently registered.

- [ ] **Step 3: Restore V1 byte-for-byte semantics and define the V2 schemas**

Keep a V1 spec with the published fields, including `version=1`, `confirmation="user"`, no `context_json`, and the existing `answer`/`session_id` output fields. Define V2 independently:

```python
v2 = CapabilitySpec(
    id="agent.interaction.chat.change.apply",
    version=2,
    owner="agent",
    description="Execute governed Agent chat and confirmation interactions with bounded event projection.",
    use_when="A governed Agent consumer sends a chat turn or confirms a pending tool interaction.",
    do_not_use_when="The request only cancels an interaction or manages Agent sessions directly.",
    risk="write",
    confirmation="none",
    idempotent=False,
    permissions=("agent.interact",),
    input_schema={
        "type": "object",
        "required": ["operation", "body"],
        "properties": {
            "operation": {"type": "string", "enum": list(OPERATIONS)},
            "body": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "session_id": {"type": ["string", "null"]},
                    "session_gid": {"type": ["string", "null"]},
                    "confirm_token": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "tool_use_id": {"type": "string"},
                    "auth_token": {"type": "string"},
                    "context_json": {"type": "string", "maxLength": 65536},
                },
                "additionalProperties": False,
            },
            "ai00_token": {"type": "string"},
        },
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "required": ["data"],
        "properties": {
            "data": {
                "type": "object",
                "properties": {
                    "events": {
                        "type": "array",
                        "maxItems": 500,
                        "items": {"type": "string"},
                    },
                    "media_type": {"type": "string"},
                    "response_json": {"type": "string", "maxLength": 1048576},
                },
                "additionalProperties": False,
            }
        },
        "additionalProperties": False,
    },
    tags=("agent", "interaction", "chat", "write"),
)
```

- [ ] **Step 4: Add separate V1/V2 adapters and register both majors**

Retain the old collector and handler for V1. The V2 adapter decodes only `context_json` and bounds output before Gateway output validation:

```python
def _decode_v2_body(raw_body: Any) -> dict[str, Any]:
    if not isinstance(raw_body, dict):
        raise ValueError("body must be an object")
    body = dict(raw_body)
    encoded = body.pop("context_json", "")
    if encoded:
        decoded = json.loads(encoded)
        if not isinstance(decoded, dict):
            raise ValueError("context_json must encode an object")
        body["context"] = decoded
    return body


async def _collect_v2(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 1048576:
            raise ValueError("synchronous response exceeds 1048576 characters")
        return {"response_json": encoded}
    iterator = getattr(value, "body_iterator", None)
    if iterator is None:
        raise ValueError("unsupported Agent response type")
    events = []
    async for chunk in iterator:
        if len(events) == 500:
            raise ValueError("stream response exceeds 500 events")
        events.append(chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
    return {"events": events, "media_type": getattr(value, "media_type", "text/event-stream")}
```

Register V1 with `descriptor_for(v1)` unchanged. Register V2 with:

```python
v2_descriptor = descriptor_for(v2_governed).model_copy(update={
    "consistency_policy": "eventual",
    "evidence_policy": "optional",
})
registry.register(v2_governed, apply_interaction_chat_change, descriptor=v2_descriptor)
```

- [ ] **Step 5: Convert the Gateway integration test to major 2**

In `test_agent_chat_runs_without_a_transaction_participant`, resolve version 2 and set the envelope to `major_version=2`. Keep the real `CapabilityGatewayService`, Catalog resolver, reliability coordinator, idempotency key, and non-transactional handler.

```python
chat = registered.get("agent.interaction.chat.change.apply", 2)
# ...
major_version=2,
```

- [ ] **Step 6: Add malformed-context and output-boundary tests**

```python
def test_agent_chat_v2_rejects_non_object_context_json():
    with pytest.raises(ValueError, match="context_json must encode an object"):
        asyncio.run(apply_interaction_chat_change(
            {"operation": "chat_sync", "body": {"message": "hi", "context_json": "[]"}},
            SimpleNamespace(user_gid="user-1"),
        ))


def test_agent_chat_v2_rejects_more_than_500_stream_events(monkeypatch):
    async def chunks():
        for _ in range(501):
            yield "data: {}\n\n"
    response = SimpleNamespace(body_iterator=chunks(), media_type="text/event-stream")
    async def stream(*_args):
        return response
    monkeypatch.setattr(ai_chat, "_legacy_chat_stream", stream)
    with pytest.raises(ValueError, match="exceeds 500 events"):
        asyncio.run(apply_interaction_chat_change(
            {"operation": "chat_stream", "body": {"message": "hi"}},
            SimpleNamespace(user_gid="user-1"),
        ))
```

- [ ] **Step 7: Run all Provider and boundary tests**

Run: `python -m pytest backend/tests/test_agent_interaction_chat_change_boundary.py plugins/agent/tests/test_agent_provider.py -q`

Expected: all tests pass, including frozen V1 and non-transactional V2 Gateway invocation.

- [ ] **Step 8: Commit both-major Provider support**

```bash
git add plugins/agent/agent_backend/capabilities/interaction_chat_change.py plugins/agent/tests/test_agent_provider.py backend/tests/test_agent_interaction_chat_change_boundary.py
git commit -m "fix(agent): add governed chat capability v2"
```

### Task 3: Pin Xiaorou Web traffic to V2 and restore transport responses

**Files:**
- Modify: `plugins/factory/factory_backend/api/compatibility.py:8-28`
- Modify: `plugins/agent/agent_backend/routers/ai_chat.py:51-64`
- Modify: `plugins/agent/agent_backend/routers/ai_chat.py:1114-1135`
- Test: `backend/tests/test_web_compatibility_adapters.py`
- Test: `backend/tests/test_agent_interaction_chat_change_boundary.py`

**Interfaces:**
- Consumes: `build_web_compatibility_envelope(..., major_version: int = 1) -> InvocationEnvelope` and `invoke_compatibility(gateway, envelope)`.
- Produces: `_normalize_interaction_payload(payload: dict) -> dict`, `_project_interaction_response(payload: dict, data: Any) -> Any`, and Web envelopes pinned to major 2 for the four chat routes.

- [ ] **Step 1: Add a failing backwards-compatibility test for major selection**

Import `SimpleNamespace` from `types` and `build_web_compatibility_envelope` from `plugins.factory.factory_backend.api.compatibility` in `backend/tests/test_web_compatibility_adapters.py`, then add:

```python
def test_factory_web_envelope_defaults_to_v1_and_accepts_explicit_major():
    gateway = SimpleNamespace(catalog_release="rel_adapter_test")
    common = dict(
        gateway=gateway,
        capability_id="agent.interaction.chat.change.apply",
        payload={"operation": "chat_sync", "body": {"message": "hi"}},
        current_user={"gid": "user-1", "team_id": "team-1", "org_role": "member"},
        principal=_principal(),
        request_id="request-1",
        trace_id="trace-1",
    )
    assert build_web_compatibility_envelope(**common).major_version == 1
    assert build_web_compatibility_envelope(**common, major_version=2).major_version == 2
```

- [ ] **Step 2: Run the builder test and confirm the keyword is rejected**

Run: `python -m pytest backend/tests/test_web_compatibility_adapters.py::test_factory_web_envelope_defaults_to_v1_and_accepts_explicit_major -q`

Expected: failure with `unexpected keyword argument 'major_version'`.

- [ ] **Step 3: Add the backwards-compatible builder argument**

```python
def build_web_compatibility_envelope(
    gateway,
    *,
    capability_id,
    payload,
    current_user,
    principal,
    request_id,
    trace_id,
    idempotency_key=None,
    approval_reference=None,
    major_version: int = 1,
):
    return InvocationEnvelope(
        capability_id=capability_id,
        major_version=major_version,
        catalog_release=gateway.catalog_release,
        payload=payload,
        identity=ConsumerIdentity(
            actor=ActorIdentity(**principal.model_dump()),
            tenant=TenantIdentity(
                tenant_id=str(current_user.get("team_id") or f"user:{current_user['gid']}"),
                membership="member",
                active_roles=tuple(filter(None, (current_user.get("org_role"), current_user.get("system_role")))),
            ),
            consumer=ConsumerDescriptor(
                type=ConsumerType.WEB,
                consumer_id="ai00.web.factory.compatibility",
            ),
        ),
        idempotency_key=idempotency_key,
        approval_reference=approval_reference,
        request_id=request_id,
        trace_id=trace_id,
    )
```

- [ ] **Step 4: Add failing Agent facade assertions for V2, identity stripping, context, SSE, and JSON**

Extend the existing boundary tests so the recording Gateway asserts:

```python
assert captured[0].major_version == 2
assert captured[0].identity.actor.user_id == "admin-1"
assert "user_gid" not in captured[0].payload["body"]
assert json.loads(captured[0].payload["body"]["context_json"]) == {
    "current_page": "workbench"
}
validate_payload(dict(v2.descriptor.input_schema), dict(captured[0].payload))
```

Keep the existing response assertions:

```python
assert response.media_type == "text/event-stream"
assert asyncio.run(collect()) == 'data: {"type":"done"}\n\n'
assert sync_response == {"answer": "ok", "tool_calls": []}
```

- [ ] **Step 5: Run the facade tests and confirm the current envelope still selects V1**

Run: `python -m pytest backend/tests/test_agent_interaction_chat_change_boundary.py -k "web_chat or web_stream or web_sync" -q`

Expected: failure because `major_version` is still 1.

- [ ] **Step 6: Normalize the request, pin major 2, and rehydrate the response**

```python
def _normalize_interaction_payload(payload: dict) -> dict:
    body = dict(payload.get("body") or {})
    context = body.pop("context", None)
    body.pop("user_gid", None)
    if context is not None:
        body["context_json"] = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    return {**payload, "body": body}


def _project_interaction_response(payload: dict, data):
    if isinstance(data, dict) and "response_json" in data:
        return json.loads(data["response_json"])
    if payload.get("operation") in {"chat_stream", "confirm"} and isinstance(data, dict):
        return StreamingResponse(
            iter(data.get("events") or ()),
            media_type=data.get("media_type") or "text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return data
```

Pass `major_version=2` to `build_web_compatibility_envelope`, validate `context` is a mapping before serialization, and leave idempotency derivation as `X-Idempotency-Key` or the server request ID.

- [ ] **Step 7: Run shared and Agent adapter regressions**

Run: `python -m pytest backend/tests/test_web_compatibility_adapters.py backend/tests/test_web_compatibility_confirmation.py backend/tests/test_agent_interaction_chat_change_boundary.py -q`

Expected: all tests pass; unrelated Factory/Project compatibility traffic remains at major 1.

- [ ] **Step 8: Commit the Web migration**

```bash
git add plugins/factory/factory_backend/api/compatibility.py plugins/agent/agent_backend/routers/ai_chat.py backend/tests/test_web_compatibility_adapters.py backend/tests/test_agent_interaction_chat_change_boundary.py
git commit -m "fix(agent): route Xiaorou chat through capability v2"
```

### Task 4: Refresh route governance and deterministic Provider/Catalog artifacts

**Files:**
- Modify: `docs/governance/legacy_route_inventory.json`
- Modify: `docs/governance/web-api-legacy-addition-review.json`
- Modify: `backend/capability_v2/official_domains.json`
- Modify: `docs/governance/capability-catalog-release.json`
- Modify: `docs/governance/capability-catalog-lineage.json`
- Modify: `backend/tests/acceptance/fixtures/case-manifest.json`
- Modify: `docs/capabilities/catalog.v2.json`
- Modify: `docs/capabilities/agent-tools.v2.json`
- Modify: `docs/capabilities/mcp-tools.v2.json`
- Modify: `docs/capabilities/openapi-fragment.v2.json`
- Modify: `docs/capabilities/.generated-manifest.json`
- Create: `docs/capabilities/agent/agent.interaction.chat.change.apply@2.md`
- Test: `backend/tests/test_capability_v2_route_inventory.py`
- Test: `backend/tests/acceptance/test_mandatory_cases.py`

**Interfaces:**
- Consumes: the final Agent Provider source, four first-party route anchors, the Catalog builder, docs generator, and acceptance-manifest generator.
- Produces: deterministic governed artifacts containing both `@1` and `@2`, with the four Xiaorou routes declaring `migration_target_major_version: 2`.

- [ ] **Step 1: Add failing route-major assertions**

In `backend/tests/test_capability_v2_route_inventory.py`, extend the existing Agent route test:

```python
agent_routes = {
    (entry.method, entry.route_path): entry
    for entry in inventory.entries
    if entry.route_path in {
        "/api/ai/chat",
        "/api/ai/chat/stream",
        "/api/ai/confirm",
        "/api/ai/confirm/sync",
    }
}
assert {entry.migration_target_major_version for entry in agent_routes.values()} == {2}
```

- [ ] **Step 2: Run the route test and confirm inventory remains on major 1**

Run: `python -m pytest backend/tests/test_capability_v2_route_inventory.py -k "agent_chat" -q`

Expected: failure showing `migration_target_major_version == 1`.

- [ ] **Step 3: Update only the four Agent route records and refresh their source anchors**

For `/api/ai/chat`, `/api/ai/chat/stream`, `/api/ai/confirm`, and `/api/ai/confirm/sync`, set:

```json
"migration_target_capability": "agent.interaction.chat.change.apply",
"migration_target_major_version": 2
```

For the same four records in `docs/governance/web-api-legacy-addition-review.json`, set `target_major_version` to 2. Because the new `major_version=2` keyword adds one source line before every handler, increment each handler anchor's `start_line` and `end_line` by one while retaining its hash. Set every binding anchor to lines 51-64, and change `expected_target_binding` to the exact call below:

```python
build_web_compatibility_envelope(
        gateway, capability_id="agent.interaction.chat.change.apply", payload=_normalize_interaction_payload(payload),
        current_user=user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=request.headers.get("X-Idempotency-Key") or request_id,
        approval_reference=request.headers.get("X-Capability-Approval"),
        major_version=2,
    )
```

Compute the one shared binding hash from the exact new line range:

```powershell
python -c "from pathlib import Path; import hashlib; p=Path('plugins/agent/agent_backend/routers/ai_chat.py'); s=''.join(p.read_text(encoding='utf-8').splitlines(keepends=True)[50:64]); print(hashlib.sha256(s.encode('utf-8')).hexdigest())"
```

Use `apply_patch` to place the printed 64-character digest in the four binding `sha256` fields. Do not change the immutable legacy baseline.

- [ ] **Step 4: Freeze the official Agent Provider hash against the exact current HEAD and manifest digest**

Record the optimistic guards:

```powershell
$integrationHead = git rev-parse HEAD
$manifestDigest = python -c "from pathlib import Path; import hashlib; p=Path('backend/capability_v2/official_domains.json'); print('sha256:'+hashlib.sha256(p.read_bytes()).hexdigest())"
python backend/scripts/freeze_official_domains.py --expected-head $integrationHead --expected-manifest-sha256 $manifestDigest
```

Expected: a new manifest digest is printed; the Agent artifact hash changes for the Agent implementation and the Factory artifact hash changes for the shared envelope implementation. No other domain artifact hash changes.

- [ ] **Step 5: Generate Catalog, docs, and acceptance manifest in dependency order**

```powershell
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
python backend/scripts/build_capability_acceptance_manifest.py --write
python backend/scripts/build_user_function_registry.py --write
```

Expected: generated files contain both `agent.interaction.chat.change.apply@1` and `@2`; the `@1` business definition hash remains frozen; `@2` has seven acceptance node IDs.

- [ ] **Step 6: Run deterministic artifact checks**

```powershell
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/build_user_function_registry.py --strict
python backend/scripts/check_domain_dependencies.py
```

Expected: every command exits 0. If a check finds unrelated pre-existing drift, record it separately; do not absorb unrelated generated changes into this task.

- [ ] **Step 7: Run both-major mandatory acceptance cases**

Run: `python -m pytest backend/tests/acceptance/test_mandatory_cases.py -k "agent.interaction.chat.change.apply" -q`

Expected: 14 cases pass: seven retained `@1` cases and seven new `@2` cases.

- [ ] **Step 8: Review generated scope and commit governance artifacts**

Run: `git diff --stat` and `git diff --check`.

Confirm no unrelated domain source or unrelated hand-edited governance record is present, then commit the exact generated set:

```bash
git add backend/capability_v2/official_domains.json backend/tests/acceptance/fixtures/case-manifest.json docs/governance/legacy_route_inventory.json docs/governance/web-api-legacy-addition-review.json docs/governance/capability-catalog-release.json docs/governance/capability-catalog-lineage.json docs/governance/user-function-registry.json docs/capabilities
git commit -m "docs(agent): publish chat capability v2 catalog"
```

### Task 5: Verify the fix and stop at the external release gates

**Files:**
- Test: `backend/tests/test_agent_interaction_chat_change_boundary.py`
- Test: `plugins/agent/tests/test_agent_provider.py`
- Test: `backend/tests/test_web_compatibility_adapters.py`
- Test: `backend/tests/test_capability_v2_route_inventory.py`
- Read: `docs/governance/capability-catalog-release.json`
- External evidence: trusted business-review record and controlled authenticated runtime report; neither is authored by this coding task.

**Interfaces:**
- Consumes: committed source/Catalog state, trusted server-authenticated business-review lookup, and a restarted backend using the refreshed Catalog.
- Produces: verified code/test commits plus an explicit release blocker report until trusted approval and runtime evidence exist.

- [ ] **Step 1: Run the full focused regression suite**

```powershell
python -m pytest backend/tests/test_agent_interaction_chat_change_boundary.py plugins/agent/tests/test_agent_provider.py backend/tests/test_web_compatibility_adapters.py backend/tests/test_web_compatibility_confirmation.py backend/tests/test_capability_v2_route_inventory.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run strict offline Capability acceptance**

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`

Expected before trusted business approval: machine checks may pass, but release readiness reports `business_definition_approval_missing:agent.interaction.chat.change.apply@2`. Treat that blocker as correct, not as a reason to edit or forge approval data.

- [ ] **Step 3: Extract the exact V2 review tuple for the super-admin workflow**

```powershell
python -c "import json; from pathlib import Path; d=json.loads(Path('docs/governance/capability-catalog-release.json').read_text(encoding='utf-8')); x=next(i for i in d['descriptors'] if i['id']=='agent.interaction.chat.change.apply' and i['major_version']==2); print(json.dumps({k:x[k] for k in ('capability_version_gid','business_definition_hash')}, ensure_ascii=False))"
```

Expected: one exact `capability_version_gid`/`business_definition_hash` pair. Submit that pair, its server-created Snapshot, and a non-empty decision reason through the trusted Capability governance Web/API workflow while authenticated as `super_admin`. Do not write the approval row directly.

- [ ] **Step 4: Re-run strict acceptance with exported trusted approval evidence**

Save the trusted server export at `.runtime/trusted-agent-chat-v2-business-approvals.json`, then run:

`python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict --business-approvals .runtime/trusted-agent-chat-v2-business-approvals.json`

Expected: `human_approved` is true only when the export's Catalog release, version GID, and definition hash exactly match the generated V2 Descriptor. A missing trusted export is an external blocker and must be reported as such.

- [ ] **Step 5: Restart the backend and exercise the authenticated Xiaorou route**

After deployment/restart loads the refreshed Catalog, send a real authenticated super-admin request to `/api/ai/chat` or `/api/ai/chat/stream` with a new request ID and idempotency key. Verify:

```text
HTTP status is not 403
HTTP status is not 422
Gateway invocation resolves agent.interaction.chat.change.apply@2
the response is valid JSON for /api/ai/chat or text/event-stream for /api/ai/chat/stream
the persisted session, when supplied, belongs to the authenticated actor
```

Capture the runtime report through the controlled runtime-verification workflow; do not encode this observation as a source-controlled assertion.

- [ ] **Step 6: Verify repository state before declaring completion**

```powershell
git status --short
git log --oneline -5
git diff --check HEAD~4..HEAD
```

Expected: the planned commits are present, no planned file remains unstaged, and unrelated pre-existing files remain untouched. Report machine, human-approval, and runtime-verification states separately.
