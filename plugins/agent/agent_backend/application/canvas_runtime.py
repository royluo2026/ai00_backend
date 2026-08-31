"""Finite Agent-owned boundary for persisted canvas execution."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal, Protocol, Self

from backend.capability_v2.secret_detection import is_sensitive_key, redact_text


MAX_INPUT_VALUES = 64
MAX_OUTPUT_VALUES = 128
MAX_OPTIONS = 200
MAX_NODE_RESULTS = 128
MAX_CONTEXT_ITEMS = 64
MAX_COLLECT_FIELDS = 32
MAX_VALUE_TEXT = 4096
MAX_ABS_NUMBER = 1_000_000_000_000

ScalarValue = str | int | float | bool | None
RuntimeValue = ScalarValue | tuple[ScalarValue, ...]
NodeStatus = Literal["ok", "error", "skipped", "warning", "pending_approval"]

_RESERVED_INPUT_PARTS = (
    "auth", "authorization", "token", "credential", "password", "passwd", "pwd",
    "secret", "apikey", "accesskey", "privatekey", "tool", "environment", "env",
    "source", "import", "path", "code", "script", "sql", "control", "command",
    "exec", "executable",
)
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
    if any(part in normalized for part in _RESERVED_INPUT_PARTS):
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
        if isinstance(self.column_width, bool) or not 120 <= self.column_width <= 1000:
            raise ValueError("column_width must be between 120 and 1000")
        if isinstance(self.lane_height, bool) or not 40 <= self.lane_height <= 500:
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


__all__ = [
    "AgentCanvasRuntime", "CanvasLayout", "CanvasOption", "CanvasOptionsRequest",
    "CanvasOptionsResult", "CanvasResumeRequest", "CanvasStartRequest", "CollectField",
    "ContextSummaryItem", "InputValue", "NodeResult", "NodeTestRequest", "NodeTestResult",
    "OutputValue", "RunPrincipal", "RuntimeDispatch", "VisibilityRule", "validated_init_params",
]
