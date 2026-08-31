"""Finite Agent-owned boundary for persisted canvas execution."""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import math
import multiprocessing
import re
import secrets
from dataclasses import asdict, dataclass
from collections.abc import Callable, Mapping
from typing import Any, Literal, Protocol, Self

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.capability_v2.secret_detection import is_sensitive_key, redact_text


MAX_INPUT_VALUES = 64
MAX_OUTPUT_VALUES = 128
MAX_OPTIONS = 200
MAX_NODE_RESULTS = 128
MAX_CONTEXT_ITEMS = 64
MAX_COLLECT_FIELDS = 32
MAX_VALUE_TEXT = 4096
MAX_ABS_NUMBER = 1_000_000_000_000
MAX_GRAPH_NODES = 128
MAX_GRAPH_EDGES = 256
MAX_GRAPH_BYTES = 262_144
MAX_INPUT_BYTES = 65_536
MAX_OUTPUT_BYTES = 65_536
DEFAULT_MAX_CONCURRENCY = 4
MAX_WORKER_ENVELOPE_BYTES = MAX_OUTPUT_BYTES + 8192

ALLOWED_NODE_TEST_KINDS = frozenset({
    "data_db", "data_mem", "data_file", "list", "human", "human_approval",
    "human_task", "fork", "join",
})

ScalarValue = str | int | float | bool | None
RuntimeValue = ScalarValue | tuple[ScalarValue, ...]
NodeStatus = Literal["ok", "error", "skipped", "warning", "pending_approval"]

_RESERVED_INPUT_NAMES = frozenset({
    "auth", "authorization", "authtoken", "token", "credential", "credentials",
    "credentialref", "password", "passwd", "pwd", "secret", "apikey", "accesskey",
    "privatekey", "tool", "toolname", "environment", "environmentid", "env", "source",
    "sourcegid", "import", "importpath", "path", "code", "pythoncode", "script", "sql",
    "rawsql", "control", "controlflag", "command", "exec", "executable", "canvas",
    "graph", "nodes",
})
_RUNTIME_CONTROL_NAMES = _RESERVED_INPUT_NAMES | frozenset({
    "sourcetool", "sourceparam", "optionsource", "optionresolver", "resolver", "resolverid",
})
_INPUT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


def _text(name: str, value: str, maximum: int = 255, *, required: bool = True) -> None:
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > maximum:
        minimum = 1 if required else 0
        raise ValueError(f"{name} must contain {minimum}-{maximum} characters")


def _safe_text(value: str) -> str:
    return redact_text(value)[0]


def _input_name(value: str) -> None:
    _text("input value name", value, 128)
    if not _INPUT_NAME.fullmatch(value):
        raise ValueError("input value name has an invalid format")
    normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
    if normalized in _RESERVED_INPUT_NAMES:
        raise ValueError("input value name uses a reserved execution-control name")


def _revision(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected_revision must be a positive integer")


def _scalar(name: str, value: ScalarValue) -> None:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > MAX_VALUE_TEXT:
            raise ValueError(f"{name} text must not exceed {MAX_VALUE_TEXT} characters")
        return
    if isinstance(value, int) and abs(value) <= MAX_ABS_NUMBER:
        return
    if isinstance(value, float) and math.isfinite(value) and abs(value) <= MAX_ABS_NUMBER:
        return
    raise ValueError(f"{name} must be within the finite numeric domain")


def _value(name: str, value: RuntimeValue) -> None:
    if isinstance(value, tuple):
        if len(value) > MAX_INPUT_VALUES:
            raise ValueError(f"{name} must contain at most {MAX_INPUT_VALUES} items")
        for item in value:
            _scalar(name, item)
        return
    _scalar(name, value)


def _redacted_value(value: RuntimeValue) -> RuntimeValue:
    if isinstance(value, tuple):
        return tuple(_safe_text(item) if isinstance(item, str) else item for item in value)
    return _safe_text(value) if isinstance(value, str) else value


def _normalized_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _is_control_key(value: object) -> bool:
    return _normalized_name(value) in _RUNTIME_CONTROL_NAMES


def _redact_recursive(value: Any, *, key: object | None = None) -> Any:
    """Canonical secret redaction plus the closed runtime-control vocabulary."""
    if key is not None and (is_sensitive_key(key) or _is_control_key(key)):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_recursive(child, key=child_key)
            for child_key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_redact_recursive(child) for child in value]
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(str(value))


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("runtime value is not finite JSON data") from exc


def _invalid(message: str) -> CapabilityBusinessError:
    return CapabilityBusinessError("invalid_input", message)


def _not_found() -> CapabilityBusinessError:
    return CapabilityBusinessError("resource_not_found", "Agent canvas resource was not found")


def _values(values: tuple["InputValue", ...], maximum: int = MAX_INPUT_VALUES) -> None:
    if not isinstance(values, tuple) or len(values) > maximum:
        raise ValueError(f"input_values must contain at most {maximum} values")
    if any(not isinstance(value, InputValue) for value in values):
        raise ValueError("input_values must contain InputValue records")
    names = [value.name for value in values]
    if len(names) != len(set(names)):
        raise ValueError("input_values names must be unique")


def _payload(payload: dict, fields: set[str]) -> None:
    unknown = sorted(set(payload) - fields)
    if unknown:
        raise ValueError("Unknown fields: " + ", ".join(unknown))


def _input_values(payload: dict) -> tuple["InputValue", ...]:
    raw = payload.get("input_values", ())
    if not isinstance(raw, (list, tuple)):
        raise ValueError("input_values must be an array")
    return tuple(
        item if isinstance(item, InputValue) else InputValue.from_payload(item)
        for item in raw
    )


@dataclass(frozen=True, slots=True)
class RunPrincipal:
    actor_gid: str
    team_gid: str

    def __post_init__(self) -> None:
        _text("actor_gid", self.actor_gid)
        _text("team_gid", self.team_gid)


@dataclass(frozen=True, slots=True)
class InputValue:
    name: str
    value: RuntimeValue

    def __post_init__(self) -> None:
        _input_name(self.name)
        _value("input value", self.value)

    @classmethod
    def from_payload(cls, payload: dict) -> Self:
        if not isinstance(payload, dict):
            raise ValueError("input value must be an object")
        _payload(payload, {"name", "value"})
        value = payload.get("value")
        return cls(name=payload.get("name", ""), value=tuple(value) if isinstance(value, list) else value)


def validated_init_params(
    values: tuple[InputValue, ...], declared_input_names: tuple[str, ...]
) -> dict[str, ScalarValue | list[ScalarValue]]:
    """Build executor init params only from the persisted node/skill input declaration."""
    _values(values)
    declared = set(declared_input_names)
    for name in declared:
        _input_name(name)
    unknown = sorted(value.name for value in values if value.name not in declared)
    if unknown:
        raise ValueError("input values are not declared by the persisted schema: " + ", ".join(unknown))
    return {
        item.name: list(item.value) if isinstance(item.value, tuple) else item.value
        for item in values
    }


@dataclass(frozen=True, slots=True)
class NodeTestRequest:
    flow_gid: str
    node_id: str
    input_values: tuple[InputValue, ...] = ()

    def __post_init__(self) -> None:
        _text("flow_gid", self.flow_gid)
        _text("node_id", self.node_id)
        _values(self.input_values)

    @classmethod
    def from_payload(cls, payload: dict) -> Self:
        _payload(payload, {"flow_gid", "node_id", "input_values"})
        return cls(str(payload.get("flow_gid") or ""), str(payload.get("node_id") or ""), _input_values(payload))


@dataclass(frozen=True, slots=True)
class CanvasOptionsRequest:
    skill_gid: str
    node_id: str
    field_key: str
    input_values: tuple[InputValue, ...] = ()

    def __post_init__(self) -> None:
        _text("skill_gid", self.skill_gid)
        _text("node_id", self.node_id)
        _input_name(self.field_key)
        _values(self.input_values)

    @classmethod
    def from_payload(cls, payload: dict) -> Self:
        _payload(payload, {"skill_gid", "node_id", "field_key", "input_values"})
        return cls(
            str(payload.get("skill_gid") or ""), str(payload.get("node_id") or ""),
            str(payload.get("field_key") or ""), _input_values(payload),
        )


@dataclass(frozen=True, slots=True)
class CanvasStartRequest:
    skill_gid: str
    expected_revision: int
    input_values: tuple[InputValue, ...] = ()

    def __post_init__(self) -> None:
        _text("skill_gid", self.skill_gid)
        _revision(self.expected_revision)
        _values(self.input_values)

    @classmethod
    def from_payload(cls, payload: dict) -> Self:
        _payload(payload, {"skill_gid", "expected_revision", "input_values"})
        return cls(
            str(payload.get("skill_gid") or ""), payload.get("expected_revision"), _input_values(payload)
        )


@dataclass(frozen=True, slots=True)
class CanvasResumeRequest:
    run_token: str
    pause_token: str
    expected_revision: int
    approved: bool
    input_values: tuple[InputValue, ...] = ()

    def __post_init__(self) -> None:
        _text("run_token", self.run_token, 512)
        _text("pause_token", self.pause_token, 512)
        _revision(self.expected_revision)
        if not isinstance(self.approved, bool):
            raise ValueError("approved must be a boolean")
        _values(self.input_values)

    @classmethod
    def from_payload(cls, payload: dict) -> Self:
        _payload(payload, {"run_token", "pause_token", "expected_revision", "approved", "input_values"})
        return cls(
            str(payload.get("run_token") or ""), str(payload.get("pause_token") or ""),
            payload.get("expected_revision"), payload.get("approved"), _input_values(payload),
        )


@dataclass(frozen=True, slots=True)
class OutputValue:
    name: str
    value: RuntimeValue

    def __post_init__(self) -> None:
        _text("output value name", self.name, 128)
        _value("output value", self.value)
        object.__setattr__(
            self, "value", "[redacted]" if is_sensitive_key(self.name) else _redacted_value(self.value)
        )


@dataclass(frozen=True, slots=True)
class NodeTestResult:
    status: Literal["completed", "rejected"]
    output_values: tuple[OutputValue, ...] = ()
    summary: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"completed", "rejected"}:
            raise ValueError("invalid node test status")
        if not isinstance(self.output_values, tuple) or len(self.output_values) > MAX_OUTPUT_VALUES:
            raise ValueError(f"output_values must contain at most {MAX_OUTPUT_VALUES} values")
        if any(not isinstance(value, OutputValue) for value in self.output_values):
            raise ValueError("output_values must contain OutputValue records")
        _text("summary", self.summary, 4000, required=False)
        object.__setattr__(self, "summary", _safe_text(self.summary))


@dataclass(frozen=True, slots=True)
class CanvasOption:
    value: str
    label: str

    def __post_init__(self) -> None:
        _text("option value", self.value, 512)
        _text("option label", self.label, 512)
        object.__setattr__(self, "value", _safe_text(self.value))
        object.__setattr__(self, "label", _safe_text(self.label))


@dataclass(frozen=True, slots=True)
class CanvasOptionsResult:
    revision: int
    options: tuple[CanvasOption, ...] = ()

    def __post_init__(self) -> None:
        _revision(self.revision)
        if not isinstance(self.options, tuple) or len(self.options) > MAX_OPTIONS:
            raise ValueError(f"options must contain at most {MAX_OPTIONS} values")
        if any(not isinstance(option, CanvasOption) for option in self.options):
            raise ValueError("options must contain CanvasOption records")


@dataclass(frozen=True, slots=True)
class NodeResult:
    node_id: str
    status: NodeStatus
    summary: str
    output_values: tuple[OutputValue, ...] = ()

    def __post_init__(self) -> None:
        _text("node_id", self.node_id)
        if self.status not in {"ok", "error", "skipped", "warning", "pending_approval"}:
            raise ValueError("invalid node result status")
        _text("node result summary", self.summary, 1000, required=False)
        if not isinstance(self.output_values, tuple) or len(self.output_values) > MAX_OUTPUT_VALUES:
            raise ValueError(f"node output_values must contain at most {MAX_OUTPUT_VALUES} values")
        if any(not isinstance(value, OutputValue) for value in self.output_values):
            raise ValueError("node output_values must contain OutputValue records")
        object.__setattr__(self, "summary", _safe_text(self.summary))


@dataclass(frozen=True, slots=True)
class ContextSummaryItem:
    node_id: str
    text: str

    def __post_init__(self) -> None:
        _text("context node_id", self.node_id)
        _text("context text", self.text, 500, required=False)
        object.__setattr__(self, "text", _safe_text(self.text))


@dataclass(frozen=True, slots=True)
class VisibilityRule:
    field_key: str
    value: ScalarValue

    def __post_init__(self) -> None:
        _input_name(self.field_key)
        _scalar("visibility value", self.value)
        object.__setattr__(self, "value", _redacted_value(self.value))


@dataclass(frozen=True, slots=True)
class CollectField:
    key: str
    label: str
    type: Literal["hidden", "radio", "select", "select_multi", "cascade"]
    options: tuple[CanvasOption, ...] = ()
    default: RuntimeValue = None
    depends_on: str | None = None
    show_when: tuple[VisibilityRule, ...] = ()

    def __post_init__(self) -> None:
        _input_name(self.key)
        _text("collect field label", self.label, 256, required=False)
        if self.type not in {"hidden", "radio", "select", "select_multi", "cascade"}:
            raise ValueError("invalid collect field type")
        if not isinstance(self.options, tuple) or len(self.options) > MAX_OPTIONS:
            raise ValueError(f"collect field options must contain at most {MAX_OPTIONS} values")
        if any(not isinstance(option, CanvasOption) for option in self.options):
            raise ValueError("collect field options must contain CanvasOption records")
        _value("collect field default", self.default)
        if self.depends_on is not None:
            _input_name(self.depends_on)
        if not isinstance(self.show_when, tuple) or len(self.show_when) > MAX_INPUT_VALUES:
            raise ValueError(f"show_when must contain at most {MAX_INPUT_VALUES} rules")
        if any(not isinstance(rule, VisibilityRule) for rule in self.show_when):
            raise ValueError("show_when must contain VisibilityRule records")
        object.__setattr__(self, "label", _safe_text(self.label))
        object.__setattr__(self, "default", _redacted_value(self.default))


@dataclass(frozen=True, slots=True)
class CanvasLayout:
    column_labels: tuple[str, ...] = ()
    column_width: int = 320
    lane_height: int = 60
    hide_lane_labels: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.column_labels, tuple) or len(self.column_labels) > 32:
            raise ValueError("column_labels must contain at most 32 labels")
        if any(not isinstance(label, str) or len(label) > 128 for label in self.column_labels):
            raise ValueError("column labels must contain at most 128 characters")
        if type(self.column_width) is not int or not 120 <= self.column_width <= 1000:
            raise ValueError("column_width must be between 120 and 1000")
        if type(self.lane_height) is not int or not 40 <= self.lane_height <= 500:
            raise ValueError("lane_height must be between 40 and 500")
        if not isinstance(self.hide_lane_labels, bool):
            raise ValueError("hide_lane_labels must be a boolean")
        object.__setattr__(self, "column_labels", tuple(_safe_text(label) for label in self.column_labels))


@dataclass(frozen=True, slots=True)
class RuntimeDispatch:
    status: Literal["accepted", "completed", "paused", "halted", "error", "outcome_unknown"]
    run_token: str
    revision: int
    pause_token: str | None = None
    halted_node_id: str | None = None
    halted_label: str | None = None
    halt_reason: str | None = None
    skill_title: str | None = None
    summary: str = ""
    node_results: tuple[NodeResult, ...] = ()
    context_summary: tuple[ContextSummaryItem, ...] = ()
    collect_fields: tuple[CollectField, ...] = ()
    canvas_layout: CanvasLayout | None = None

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "completed", "paused", "halted", "error", "outcome_unknown"}:
            raise ValueError("invalid runtime dispatch status")
        _text("run_token", self.run_token, 512)
        _revision(self.revision)
        if self.status == "paused" and not all((self.pause_token, self.halted_node_id, self.halted_label)):
            raise ValueError("paused runtime dispatch requires pause_token and paused node identity")
        for name, value, maximum in (
            ("pause_token", self.pause_token, 512), ("halted_node_id", self.halted_node_id, 255),
            ("halted_label", self.halted_label, 256), ("halt_reason", self.halt_reason, 4000),
            ("skill_title", self.skill_title, 256),
        ):
            if value is not None:
                _text(name, value, maximum)
        _text("summary", self.summary, 4000, required=False)
        if not isinstance(self.node_results, tuple) or len(self.node_results) > MAX_NODE_RESULTS:
            raise ValueError(f"node_results must contain at most {MAX_NODE_RESULTS} results")
        if any(not isinstance(item, NodeResult) for item in self.node_results):
            raise ValueError("node_results must contain NodeResult records")
        if not isinstance(self.context_summary, tuple) or len(self.context_summary) > MAX_CONTEXT_ITEMS:
            raise ValueError(f"context_summary must contain at most {MAX_CONTEXT_ITEMS} items")
        if any(not isinstance(item, ContextSummaryItem) for item in self.context_summary):
            raise ValueError("context_summary must contain ContextSummaryItem records")
        if not isinstance(self.collect_fields, tuple) or len(self.collect_fields) > MAX_COLLECT_FIELDS:
            raise ValueError(f"collect_fields must contain at most {MAX_COLLECT_FIELDS} fields")
        if any(not isinstance(item, CollectField) for item in self.collect_fields):
            raise ValueError("collect_fields must contain CollectField records")
        if self.canvas_layout is not None and not isinstance(self.canvas_layout, CanvasLayout):
            raise ValueError("canvas_layout must be CanvasLayout")
        for name in ("halted_label", "halt_reason", "skill_title", "summary"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _safe_text(value))


class AgentCanvasRuntime(Protocol):
    async def test_node(self, request: NodeTestRequest, principal: RunPrincipal) -> NodeTestResult: ...

    async def resolve_options(self, request: CanvasOptionsRequest, principal: RunPrincipal) -> CanvasOptionsResult: ...

    async def start(self, request: CanvasStartRequest, principal: RunPrincipal) -> RuntimeDispatch: ...

    async def resume(self, request: CanvasResumeRequest, principal: RunPrincipal) -> RuntimeDispatch: ...


class _CanvasQueryEngine:
    """Synchronous dependencies and closed projection, run only inside an isolated worker."""

    def __init__(
        self,
        *,
        resource_loader: Callable[[str, str], Mapping[str, Any] | None],
        executor_factory: Callable[..., Any] | None = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer")
        self._resource_loader = resource_loader
        self._executor_factory = executor_factory or self._canvas_executor
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @staticmethod
    def _canvas_executor(**kwargs):
        from ..ai_assistant.canvas_executor import CanvasExecutor

        return CanvasExecutor(**kwargs)

    @staticmethod
    def _authorize(kind: str, row: Mapping[str, Any], principal: RunPrincipal) -> None:
        persisted_team = str(row.get("team_gid") or "")
        if persisted_team != principal.team_gid:
            raise _not_found()
        if kind == "flow":
            if str(row.get("owner_user_gid") or "") != principal.actor_gid:
                raise _not_found()
            return
        scope = str(row.get("scope") or "private")
        owner = str(row.get("owner_gid") or "")
        if scope == "private" and owner == principal.actor_gid:
            return
        if scope == "team":
            return
        if scope == "global" and str(row.get("status") or "") == "active":
            return
        raise _not_found()

    def _record(self, kind: str, gid: str, principal: RunPrincipal) -> Mapping[str, Any]:
        row = self._resource_loader(kind, gid)
        if not isinstance(row, Mapping):
            raise _not_found()
        self._authorize(kind, row, principal)
        return row

    @staticmethod
    def _document(kind: str, row: Mapping[str, Any]) -> dict[str, Any]:
        raw = row.get("flowdef") if kind == "flow" else row.get("content")
        if isinstance(raw, str):
            if len(raw.encode("utf-8")) > MAX_GRAPH_BYTES:
                raise _invalid("persisted canvas graph exceeds the size limit")
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    import yaml

                    raw = yaml.safe_load(raw)
                except Exception as exc:
                    raise _invalid("persisted canvas graph is invalid") from exc
        if not isinstance(raw, Mapping):
            raise _invalid("persisted canvas graph is invalid")
        nested = raw.get("canvas")
        document = dict(nested if isinstance(nested, Mapping) else raw)
        if len(_json_bytes(document)) > MAX_GRAPH_BYTES:
            raise _invalid("persisted canvas graph exceeds the size limit")
        nodes = document.get("nodes", [])
        edges = document.get("edges", document.get("connections", []))
        if not isinstance(nodes, list) or len(nodes) > MAX_GRAPH_NODES:
            raise _invalid(f"persisted canvas graph must contain at most {MAX_GRAPH_NODES} nodes")
        if not isinstance(edges, list) or len(edges) > MAX_GRAPH_EDGES:
            raise _invalid(f"persisted canvas graph must contain at most {MAX_GRAPH_EDGES} edges")
        if any(not isinstance(node, Mapping) for node in nodes):
            raise _invalid("persisted canvas graph contains an invalid node")
        return document

    @staticmethod
    def _node(document: Mapping[str, Any], node_id: str) -> Mapping[str, Any]:
        matches = [node for node in document.get("nodes", []) if str(node.get("id") or "") == node_id]
        if len(matches) != 1:
            raise _not_found()
        return matches[0]

    @staticmethod
    def _declared_input_names(document: Mapping[str, Any], node: Mapping[str, Any]) -> tuple[str, ...]:
        schema = node.get("inputs_schema") or node.get("input_schema")
        if schema is None:
            schema = document.get("inputs_schema") or document.get("input_schema") or {}
        if not isinstance(schema, Mapping):
            raise _invalid("persisted input schema is invalid")
        properties = schema.get("properties")
        names = properties.keys() if isinstance(properties, Mapping) else schema.keys()
        return tuple(str(name) for name in names)

    @classmethod
    def _init_params(
        cls,
        document: Mapping[str, Any],
        node: Mapping[str, Any],
        values: tuple[InputValue, ...],
    ) -> dict[str, ScalarValue | list[ScalarValue]]:
        try:
            params = validated_init_params(values, cls._declared_input_names(document, node))
        except ValueError as exc:
            raise _invalid(str(exc)) from exc
        if len(_json_bytes(params)) > MAX_INPUT_BYTES:
            raise _invalid("runtime input exceeds the size limit")
        return params

    @staticmethod
    def _project_value(name: str, value: Any) -> RuntimeValue:
        safe = _redact_recursive(value, key=name)
        if safe is None or isinstance(safe, (str, bool, int, float)):
            return safe
        if isinstance(safe, list) and len(safe) <= MAX_INPUT_VALUES and all(
            child is None or isinstance(child, (str, bool, int, float)) for child in safe
        ):
            return tuple(safe)
        return _json_bytes(safe).decode("utf-8")

    @classmethod
    def _node_result(cls, raw: Any, node_id: str) -> NodeTestResult:
        if not isinstance(raw, Mapping):
            raise _invalid("runtime output is invalid")
        safe_raw = _redact_recursive(raw)
        if len(_json_bytes(safe_raw)) > MAX_OUTPUT_BYTES:
            raise _invalid("runtime output exceeds the size limit")
        results = raw.get("node_results")
        node_result = results.get(node_id) if isinstance(results, Mapping) else None
        if not isinstance(node_result, Mapping):
            raise _invalid("runtime output omitted the requested node")
        public = [(str(key), value) for key, value in node_result.items() if not str(key).startswith("_")]
        if len(public) > MAX_OUTPUT_VALUES:
            raise _invalid("runtime output contains too many values")
        try:
            output_values = tuple(
                OutputValue(name, cls._project_value(name, value))
                for name, value in sorted(public, key=lambda item: item[0])
            )
            summary = str(node_result.get("_summary") or raw.get("summary") or "")
            rejected = node_result.get("_status") == "error" or raw.get("status") == "error"
            return NodeTestResult("rejected" if rejected else "completed", output_values, summary)
        except ValueError as exc:
            raise _invalid("runtime output exceeded the closed projection limits") from exc

    async def test_node(self, request: NodeTestRequest, principal: RunPrincipal) -> NodeTestResult:
        async with self._semaphore:
            row = self._record("flow", request.flow_gid, principal)
            document = self._document("flow", row)
            node = self._node(document, request.node_id)
            kind = str(node.get("type") or "")
            if kind not in ALLOWED_NODE_TEST_KINDS:
                raise _invalid("persisted node kind is not allowed for bounded testing")
            init_params = self._init_params(document, node, request.input_values)
            raw_params = node.get("params") if isinstance(node.get("params"), Mapping) else node.get("config", {})
            params = dict(raw_params) if isinstance(raw_params, Mapping) else {}
            bounded_node = {
                "id": request.node_id,
                "type": kind,
                "label": str(node.get("label") or kind),
                "params": params,
            }
            executor = self._executor_factory(
                auth_mode="feishu", auth_token="", owner_gid=principal.actor_gid,
            )
            result = executor.execute({"nodes": [bounded_node]}, init_params=init_params)
            if inspect.isawaitable(result):
                result = await result
            return self._node_result(result, request.node_id)

    async def resolve_options(
        self, request: CanvasOptionsRequest, principal: RunPrincipal
    ) -> CanvasOptionsResult:
        async with self._semaphore:
            row = self._record("skill", request.skill_gid, principal)
            document = self._document("skill", row)
            node = self._node(document, request.node_id)
            self._init_params(document, node, request.input_values)
            params = node.get("params") if isinstance(node.get("params"), Mapping) else node.get("config", {})
            fields = params.get("collect_fields", []) if isinstance(params, Mapping) else []
            if not isinstance(fields, list) or len(fields) > MAX_COLLECT_FIELDS:
                raise _invalid("persisted option fields are invalid")
            matches = [field for field in fields if isinstance(field, Mapping) and field.get("key") == request.field_key]
            if len(matches) != 1:
                raise _not_found()
            field = matches[0]
            if any(_is_control_key(key) for key in field if key not in {"key", "label", "type", "options"}):
                raise _invalid("persisted option field requests an executable resolver")
            raw_options = field.get("options", [])
            if not isinstance(raw_options, list) or len(raw_options) > MAX_OPTIONS:
                raise _invalid(f"persisted options must contain at most {MAX_OPTIONS} values")
            try:
                options = tuple(CanvasOption(str(option["value"]), str(option["label"])) for option in raw_options)
            except (KeyError, TypeError, ValueError) as exc:
                raise _invalid("persisted options are invalid") from exc
            options = tuple(sorted(
                options,
                key=lambda option: (
                    option.label.casefold(), option.value.casefold(), option.label, option.value,
                ),
            ))
            if len(_json_bytes([{"value": item.value, "label": item.label} for item in options])) > MAX_OUTPUT_BYTES:
                raise _invalid("runtime output exceeds the size limit")
            revision = row.get("revision", document.get("revision", 1))
            try:
                return CanvasOptionsResult(revision=revision, options=options)
            except ValueError as exc:
                raise _invalid("persisted option revision is invalid") from exc


class _CanvasCommandEngine(_CanvasQueryEngine):
    """Run a stored skill and rebuild only the bounded checkpoint needed by resume."""

    def __init__(
        self, *, resource_loader, execution_loader, executor_factory=None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        super().__init__(
            resource_loader=resource_loader, executor_factory=executor_factory,
            max_concurrency=max_concurrency,
        )
        self._execution_loader = execution_loader

    @staticmethod
    def _status(value: object) -> NodeStatus:
        normalized = str(value or "ok")
        return normalized if normalized in {"ok", "error", "skipped", "warning", "pending_approval"} else "warning"

    @classmethod
    def _node_results(cls, raw: Mapping[str, Any]) -> tuple[NodeResult, ...]:
        values = raw.get("node_results")
        if not isinstance(values, Mapping) or len(values) > MAX_NODE_RESULTS:
            raise _invalid("runtime output contains invalid node results")
        result = []
        for node_id, item in sorted(values.items(), key=lambda pair: str(pair[0])):
            if not isinstance(item, Mapping):
                raise _invalid("runtime output contains an invalid node result")
            public = [(str(key), value) for key, value in item.items() if not str(key).startswith("_")]
            if len(public) > MAX_OUTPUT_VALUES:
                raise _invalid("runtime node output contains too many values")
            result.append(NodeResult(
                str(node_id), cls._status(item.get("_status")),
                str(item.get("_summary") or ""),
                tuple(OutputValue(name, cls._project_value(name, value)) for name, value in public),
            ))
        return tuple(result)

    @staticmethod
    def _paused_node(document: Mapping[str, Any], node_id: str | None) -> Mapping[str, Any] | None:
        if not node_id:
            return None
        matches = [node for node in document.get("nodes", ()) if str(node.get("id") or "") == node_id]
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def _pause_projection(cls, document, raw):
        node = cls._paused_node(document, str(raw.get("halted_node_id") or ""))
        if node is None:
            return (), None
        params = node.get("params") if isinstance(node.get("params"), Mapping) else {}
        raw_fields = params.get("collect_fields") or []
        if not isinstance(raw_fields, list) or len(raw_fields) > MAX_COLLECT_FIELDS:
            raise _invalid("persisted collect fields are invalid")
        fields = []
        for item in raw_fields:
            if not isinstance(item, Mapping):
                raise _invalid("persisted collect field is invalid")
            options = item.get("options") or []
            if not isinstance(options, list) or len(options) > MAX_OPTIONS:
                raise _invalid("persisted collect field options are invalid")
            show_when = item.get("show_when") or []
            if isinstance(show_when, Mapping):
                show_when = [
                    {"field_key": str(key), "value": value}
                    for key, value in show_when.items()
                ]
            if not isinstance(show_when, list):
                raise _invalid("persisted collect field visibility is invalid")
            default = item.get("default")
            try:
                fields.append(CollectField(
                    key=str(item.get("key") or ""), label=str(item.get("label") or ""),
                    type=item.get("type"),
                    options=tuple(CanvasOption(str(value["value"]), str(value["label"])) for value in options),
                    default=tuple(default) if isinstance(default, list) else default,
                    depends_on=item.get("depends_on"),
                    show_when=tuple(VisibilityRule(
                        str(value.get("field_key") or ""), value.get("value"),
                    ) for value in show_when),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise _invalid("persisted collect field is invalid") from exc
        layout = params.get("canvas_layout")
        if layout is None:
            return tuple(fields), None
        if not isinstance(layout, Mapping):
            raise _invalid("persisted canvas layout is invalid")
        try:
            public_layout = CanvasLayout(
                column_labels=tuple(layout.get("column_labels") or ()),
                column_width=layout.get("column_width", 320),
                lane_height=layout.get("lane_height", 60),
                hide_lane_labels=layout.get("hide_lane_labels", False),
            )
        except ValueError as exc:
            raise _invalid("persisted canvas layout is invalid") from exc
        return tuple(fields), public_layout

    @classmethod
    def _project(cls, raw, document, row, *, run_token, revision):
        if not isinstance(raw, Mapping):
            raise _invalid("runtime output is invalid")
        safe = _redact_recursive(raw)
        if len(_json_bytes(safe)) > MAX_OUTPUT_BYTES:
            raise _invalid("runtime output exceeds the size limit")
        status = str(raw.get("status") or "error")
        if status not in {"completed", "paused", "halted", "error"}:
            raise _invalid("runtime output has an invalid status")
        fields, layout = cls._pause_projection(document, raw) if status == "paused" else ((), None)
        return RuntimeDispatch(
            status=status, run_token=run_token, revision=revision,
            pause_token=(secrets.token_urlsafe(32) if status == "paused" else None),
            halted_node_id=(str(raw.get("halted_node_id")) if raw.get("halted_node_id") else None),
            halted_label=(str(raw.get("halted_label")) if raw.get("halted_label") else None),
            halt_reason=(str(raw.get("halt_reason")) if raw.get("halt_reason") else None),
            skill_title=(str(row.get("title")) if row.get("title") else None),
            summary=str(raw.get("summary") or ""), node_results=cls._node_results(raw),
            collect_fields=fields, canvas_layout=layout,
        )

    @staticmethod
    def _restore(checkpoint: Mapping[str, Any], halted_node_id: str, values) -> dict[str, dict]:
        restored = {}
        for item in checkpoint.get("node_results") or ():
            if not isinstance(item, Mapping):
                raise _invalid("stored canvas checkpoint is invalid")
            node_id = str(item.get("node_id") or "")
            raw = {
                "_status": "ok" if node_id == halted_node_id else str(item.get("status") or "warning"),
                "_summary": "Approved" if node_id == halted_node_id else str(item.get("summary") or ""),
            }
            for output in item.get("output_values") or ():
                if isinstance(output, Mapping):
                    raw[str(output.get("name") or "")] = output.get("value")
            if node_id == halted_node_id:
                raw.update({item.name: list(item.value) if isinstance(item.value, tuple) else item.value for item in values})
            restored[node_id] = raw
        return restored

    async def start(self, request, principal, *, run_token):
        async with self._semaphore:
            row = self._record("skill", request.skill_gid, principal)
            document = self._document("skill", row)
            if int(row.get("revision", document.get("revision", 1))) != request.expected_revision:
                raise CapabilityBusinessError("version_conflict", "Agent canvas revision changed")
            init_params = self._init_params(document, {}, request.input_values)
            executor = self._executor_factory(auth_mode="feishu", auth_token="", owner_gid=principal.actor_gid)
            raw = executor.execute(document, init_params=init_params)
            if inspect.isawaitable(raw):
                raw = await raw
            return self._project(raw, document, row, run_token=run_token, revision=1)

    async def resume(self, request, principal, *, run_token):
        async with self._semaphore:
            state = self._execution_loader(request.run_token, principal.actor_gid, principal.team_gid)
            checkpoint = state.get("checkpoint") if isinstance(state, Mapping) else None
            if not isinstance(state, Mapping) or not isinstance(checkpoint, Mapping):
                raise _not_found()
            if (
                checkpoint.get("pause_token") != request.pause_token
                or int(checkpoint.get("revision") or 0) != request.expected_revision
                or int(state.get("revision") or 0) not in {request.expected_revision, request.expected_revision + 1}
            ):
                raise _not_found()
            row = self._record("skill", str(state.get("skill_gid") or ""), principal)
            document = self._document("skill", row)
            if int(row.get("revision", document.get("revision", 1))) != int(state.get("skill_revision") or 0):
                raise CapabilityBusinessError("version_conflict", "Agent canvas revision changed")
            halted_node_id = str(checkpoint.get("halted_node_id") or "")
            node = self._node(document, halted_node_id)
            self._init_params(document, node, request.input_values)
            restored = self._restore(checkpoint, halted_node_id, request.input_values)
            if not request.approved:
                raw = {
                    "status": "halted", "halted_node_id": halted_node_id,
                    "halted_label": checkpoint.get("halted_label"),
                    "halt_reason": "The human step was rejected.", "summary": "The flow was rejected.",
                    "node_results": restored,
                }
                return self._project(
                    raw, document, row, run_token=run_token, revision=request.expected_revision + 1,
                )
            executor = self._executor_factory(auth_mode="feishu", auth_token="", owner_gid=principal.actor_gid)
            raw = executor.execute(document, restore_results=restored)
            if inspect.isawaitable(raw):
                raw = await raw
            return self._project(
                raw, document, row, run_token=run_token, revision=request.expected_revision + 1,
            )


def _dispatch_from_worker(value: Mapping[str, Any]) -> RuntimeDispatch:
    def output(item):
        raw = item.get("value")
        return OutputValue(str(item.get("name") or ""), tuple(raw) if isinstance(raw, list) else raw)

    layout = value.get("canvas_layout")
    fields = []
    for item in value.get("collect_fields") or ():
        default = item.get("default")
        fields.append(CollectField(
            key=str(item.get("key") or ""), label=str(item.get("label") or ""), type=item.get("type"),
            options=tuple(CanvasOption(str(child["value"]), str(child["label"])) for child in item.get("options") or ()),
            default=tuple(default) if isinstance(default, list) else default,
            depends_on=item.get("depends_on"),
            show_when=tuple(VisibilityRule(
                str(child.get("field_key") or ""), child.get("value"),
            ) for child in item.get("show_when") or ()),
        ))
    return RuntimeDispatch(
        status=value.get("status"), run_token=str(value.get("run_token") or ""),
        revision=value.get("revision"), pause_token=value.get("pause_token"),
        halted_node_id=value.get("halted_node_id"), halted_label=value.get("halted_label"),
        halt_reason=value.get("halt_reason"), skill_title=value.get("skill_title"),
        summary=str(value.get("summary") or ""),
        node_results=tuple(NodeResult(
            str(item.get("node_id") or ""), item.get("status"), str(item.get("summary") or ""),
            tuple(output(child) for child in item.get("output_values") or ()),
        ) for item in value.get("node_results") or ()),
        context_summary=tuple(ContextSummaryItem(
            str(item.get("node_id") or ""), str(item.get("text") or ""),
        ) for item in value.get("context_summary") or ()),
        collect_fields=tuple(fields),
        canvas_layout=(CanvasLayout(
            column_labels=tuple(layout.get("column_labels") or ()),
            column_width=layout.get("column_width", 320), lane_height=layout.get("lane_height", 60),
            hide_lane_labels=layout.get("hide_lane_labels", False),
        ) if isinstance(layout, Mapping) else None),
    )

def _factory_path(factory: Callable[..., Any] | None) -> str:
    if factory is None:
        return "plugins.agent.agent_backend.infrastructure.repository:AgentCapabilityRepository"
    module = getattr(factory, "__module__", "")
    name = getattr(factory, "__qualname__", "")
    if not module or not name or "<locals>" in name:
        raise ValueError("repository_factory must be a module-level callable")
    return f"{module}:{name}"


def _load_factory(path: str) -> Callable[..., Any]:
    module_name, _, qualname = path.partition(":")
    value: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        value = getattr(value, part)
    return value


def _worker_error(error: CapabilityBusinessError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
        "details": _redact_recursive(error.details),
    }


def _worker_envelope_bytes(envelope: Mapping[str, Any]) -> bytes:
    raw = json.dumps(
        envelope, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    if len(raw) <= MAX_WORKER_ENVELOPE_BYTES:
        return raw
    return json.dumps({
        "ok": False,
        "error": _worker_error(_invalid("runtime output exceeds the size limit")),
    }, separators=(",", ":")).encode("utf-8")


def _canvas_query_worker(result_connection: Any, payload_json: str) -> None:
    """Own the database connection and the one existing executor in a terminable process."""
    try:
        payload = json.loads(payload_json)
        principal = RunPrincipal(**payload["principal"])
        request_payload = payload["request"]
        repository = _load_factory(payload["repository_factory"])()
        engine = _CanvasQueryEngine(
            resource_loader=lambda kind, gid: repository.load_canvas_resource(
                kind, gid, principal.actor_gid, principal.team_gid,
            ),
        )
        operation = payload["operation"]
        if operation == "test_node":
            result = asyncio.run(engine.test_node(NodeTestRequest.from_payload(request_payload), principal))
        elif operation == "resolve_options":
            result = asyncio.run(engine.resolve_options(CanvasOptionsRequest.from_payload(request_payload), principal))
        elif operation in {"start", "resume"}:
            command = _CanvasCommandEngine(
                resource_loader=lambda kind, gid: repository.load_canvas_resource(
                    kind, gid, principal.actor_gid, principal.team_gid,
                ),
                execution_loader=repository.load_canvas_execution_state,
            )
            request = (
                CanvasStartRequest.from_payload(request_payload)
                if operation == "start" else CanvasResumeRequest.from_payload(request_payload)
            )
            result = asyncio.run(getattr(command, operation)(
                request, principal, run_token=str(payload.get("run_token") or request_payload.get("run_token") or ""),
            ))
        else:
            raise _invalid("unsupported Agent canvas query operation")
        envelope = {"ok": True, "result": asdict(result)}
    except CapabilityBusinessError as error:
        envelope = {"ok": False, "error": _worker_error(error)}
    except (TypeError, ValueError) as error:
        envelope = {"ok": False, "error": _worker_error(_invalid(str(error)))}
    except Exception:
        envelope = {"ok": False, "error": _worker_error(CapabilityBusinessError(
            "provider_unavailable", "Agent canvas query provider is unavailable", retryable=True,
        ))}
    try:
        result_connection.send_bytes(_worker_envelope_bytes(envelope))
    finally:
        result_connection.close()


class ProductionAgentCanvasRuntime:
    """Bounded async port supervising all blocking resource/executor work in a spawned process."""

    def __init__(
        self,
        *,
        repository_factory: Callable[..., Any] | None = None,
        worker_target: Callable[[Any, str], None] = _canvas_query_worker,
        worker_timeout: float = 2.5,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        if isinstance(worker_timeout, bool) or not isinstance(worker_timeout, (int, float)) or worker_timeout <= 0:
            raise ValueError("worker_timeout must be positive")
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer")
        self._repository_factory = _factory_path(repository_factory)
        self._worker_target = worker_target
        self._worker_timeout = float(worker_timeout)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @staticmethod
    def _stop(process: Any) -> None:
        if process.is_alive():
            process.terminate()
            process.join(1.0)
        if process.is_alive():
            process.kill()
            process.join(1.0)

    async def _run_process(
        self, operation: str, request: Any, principal: RunPrincipal, *,
        run_token: str | None = None, invocation_id: str | None = None,
    ) -> dict[str, Any]:
        payload_json = json.dumps({
            "operation": operation,
            "request": asdict(request),
            "principal": asdict(principal),
            "repository_factory": self._repository_factory,
            "run_token": run_token,
            "invocation_id": invocation_id,
        }, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        context = multiprocessing.get_context("spawn")
        result_connection, worker_connection = context.Pipe(duplex=False)
        process = context.Process(target=self._worker_target, args=(worker_connection, payload_json))
        started = False
        try:
            process.start()
            started = True
            worker_connection.close()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._worker_timeout
            raw = None
            while loop.time() < deadline:
                if result_connection.poll(0):
                    try:
                        raw = result_connection.recv_bytes(MAX_WORKER_ENVELOPE_BYTES)
                    except OSError as exc:
                        raise _invalid("runtime output exceeds the size limit") from exc
                    break
                if not process.is_alive():
                    if result_connection.poll(0.05):
                        continue
                    raise CapabilityBusinessError(
                        "provider_unavailable", "Agent canvas query provider is unavailable", retryable=True,
                    )
                await asyncio.sleep(0.005)
            if raw is None:
                self._stop(process)
                raise CapabilityBusinessError(
                    "runtime_timeout", "Agent canvas runtime timed out", retryable=True,
                )
            while process.is_alive() and loop.time() < deadline:
                await asyncio.sleep(0.005)
            if process.is_alive():
                self._stop(process)
                raise CapabilityBusinessError(
                    "runtime_timeout", "Agent canvas runtime timed out", retryable=True,
                )
            process.join()
            try:
                envelope = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CapabilityBusinessError(
                    "provider_unavailable", "Agent canvas query provider is unavailable", retryable=True,
                ) from exc
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise CapabilityBusinessError(
                    str(error.get("code") or "provider_unavailable"),
                    str(error.get("message") or "Agent canvas query provider is unavailable"),
                    retryable=bool(error.get("retryable")),
                    details=error.get("details") if isinstance(error.get("details"), Mapping) else {},
                )
            result = envelope.get("result")
            if not isinstance(result, dict):
                raise CapabilityBusinessError(
                    "provider_unavailable", "Agent canvas query provider is unavailable", retryable=True,
                )
            return result
        finally:
            if started:
                self._stop(process)
                process.close()
            worker_connection.close()
            result_connection.close()

    async def test_node(self, request: NodeTestRequest, principal: RunPrincipal) -> NodeTestResult:
        async with self._semaphore:
            result = await self._run_process("test_node", request, principal)
        try:
            output_values = tuple(OutputValue(**item) for item in result.get("output_values", ()))
            return NodeTestResult(
                status=result.get("status"), output_values=output_values,
                summary=str(result.get("summary") or ""),
            )
        except (TypeError, ValueError) as exc:
            raise _invalid("runtime output is invalid") from exc

    async def resolve_options(
        self, request: CanvasOptionsRequest, principal: RunPrincipal,
    ) -> CanvasOptionsResult:
        async with self._semaphore:
            result = await self._run_process("resolve_options", request, principal)
        try:
            options = tuple(CanvasOption(**item) for item in result.get("options", ()))
            return CanvasOptionsResult(revision=result.get("revision"), options=options)
        except (TypeError, ValueError) as exc:
            raise _invalid("runtime output is invalid") from exc

    async def start(self, request: CanvasStartRequest, principal: RunPrincipal) -> RuntimeDispatch:
        return await self.execute_canvas_command(
            "start", request, principal, run_token=f"run_{secrets.token_urlsafe(32)}",
            invocation_id=f"invocation_{secrets.token_urlsafe(32)}",
        )

    async def resume(self, request: CanvasResumeRequest, principal: RunPrincipal) -> RuntimeDispatch:
        return await self.execute_canvas_command(
            "resume", request, principal, run_token=request.run_token,
            invocation_id=f"invocation_{secrets.token_urlsafe(32)}",
        )

    async def execute_canvas_command(
        self, operation: str, request: CanvasStartRequest | CanvasResumeRequest,
        principal: RunPrincipal, *, run_token: str, invocation_id: str,
    ) -> RuntimeDispatch:
        if operation not in {"start", "resume"}:
            raise _invalid("unsupported Agent canvas command operation")
        async with self._semaphore:
            result = await self._run_process(
                operation, request, principal, run_token=run_token, invocation_id=invocation_id,
            )
        try:
            return _dispatch_from_worker(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid("runtime output is invalid") from exc

    async def reconcile_canvas_command(
        self, operation: str, request: CanvasStartRequest | CanvasResumeRequest,
        principal: RunPrincipal, *, run_token: str, invocation_id: str,
    ) -> RuntimeDispatch:
        del principal, invocation_id
        revision = 1 if operation == "start" else request.expected_revision + 1
        return RuntimeDispatch(
            "outcome_unknown", run_token, revision,
            summary="The runtime outcome requires reconciliation.",
        )

__all__ = [
    "AgentCanvasRuntime", "CanvasLayout", "CanvasOption", "CanvasOptionsRequest",
    "CanvasOptionsResult", "CanvasResumeRequest", "CanvasStartRequest", "CollectField",
    "ContextSummaryItem", "InputValue", "NodeResult", "NodeTestRequest", "NodeTestResult",
    "OutputValue", "ProductionAgentCanvasRuntime", "RunPrincipal", "RuntimeDispatch",
    "VisibilityRule", "validated_init_params",
]
