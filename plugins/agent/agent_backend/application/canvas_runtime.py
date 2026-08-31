"""Finite Agent-owned boundary for persisted canvas execution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Self


MAX_INPUT_VALUES = 64
MAX_OUTPUT_VALUES = 128
MAX_OPTIONS = 200
MAX_VALUE_TEXT = 4096

ScalarValue = str | int | float | bool | None
RuntimeValue = ScalarValue | tuple[ScalarValue, ...]


def _text(name: str, value: str, maximum: int = 255) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain 1-{maximum} characters")


def _revision(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected_revision must be a positive integer")


def _scalar(name: str, value: ScalarValue) -> None:
    if not (value is None or isinstance(value, (str, int, float, bool))):
        raise ValueError(f"{name} must be scalar")
    if isinstance(value, str) and len(value) > MAX_VALUE_TEXT:
        raise ValueError(f"{name} text must not exceed {MAX_VALUE_TEXT} characters")


def _value(name: str, value: RuntimeValue) -> None:
    if isinstance(value, tuple):
        if len(value) > MAX_INPUT_VALUES:
            raise ValueError(f"{name} must contain at most {MAX_INPUT_VALUES} items")
        for item in value:
            _scalar(name, item)
        return
    _scalar(name, value)


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
        _text("input value name", self.name, 128)
        _value("input value", self.value)

    @classmethod
    def from_payload(cls, payload: dict) -> Self:
        if not isinstance(payload, dict):
            raise ValueError("input value must be an object")
        _payload(payload, {"name", "value"})
        value = payload.get("value")
        return cls(name=payload.get("name", ""), value=tuple(value) if isinstance(value, list) else value)


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
        _text("field_key", self.field_key, 128)
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
        if len(self.summary) > 4000:
            raise ValueError("summary must not exceed 4000 characters")


@dataclass(frozen=True, slots=True)
class CanvasOption:
    value: str
    label: str

    def __post_init__(self) -> None:
        _text("option value", self.value, 512)
        _text("option label", self.label, 512)


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
class RuntimeDispatch:
    status: Literal["accepted", "completed", "paused", "outcome_unknown"]
    run_token: str
    revision: int
    pause_token: str | None = None
    summary: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "completed", "paused", "outcome_unknown"}:
            raise ValueError("invalid runtime dispatch status")
        _text("run_token", self.run_token, 512)
        _revision(self.revision)
        if self.status == "paused" and self.pause_token is None:
            raise ValueError("paused runtime dispatch requires pause_token")
        if self.pause_token is not None:
            _text("pause_token", self.pause_token, 512)
        if len(self.summary) > 4000:
            raise ValueError("summary must not exceed 4000 characters")


class AgentCanvasRuntime(Protocol):
    async def test_node(self, request: NodeTestRequest, principal: RunPrincipal) -> NodeTestResult: ...

    async def resolve_options(self, request: CanvasOptionsRequest, principal: RunPrincipal) -> CanvasOptionsResult: ...

    async def start(self, request: CanvasStartRequest, principal: RunPrincipal) -> RuntimeDispatch: ...

    async def resume(self, request: CanvasResumeRequest, principal: RunPrincipal) -> RuntimeDispatch: ...


__all__ = [
    "AgentCanvasRuntime", "CanvasOption", "CanvasOptionsRequest", "CanvasOptionsResult",
    "CanvasResumeRequest", "CanvasStartRequest", "InputValue", "NodeTestRequest",
    "NodeTestResult", "OutputValue", "RunPrincipal", "RuntimeDispatch",
]
