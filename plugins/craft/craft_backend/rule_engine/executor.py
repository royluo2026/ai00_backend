"""
backend/rule_engine/executor.py
────────────────────────────────
CEL 表达式执行器。返回四态结果：PASS / WARN / FAIL / SKIP。

依赖：cel-python（pip install cel-python），缺失时所有规则返回 SKIP。
"""
from __future__ import annotations

import logging
import re
from enum import Enum

_log = logging.getLogger(__name__)
_CEL_TOKEN = re.compile(
    r"\s*(?:(?P<number>0|[1-9][0-9]*)(?:\.[0-9]+)?|"
    r"(?P<string>'(?:[^'\\\n\r]|\\.)*'|\"(?:[^\"\\\n\r]|\\.)*\")|"
    r"(?P<operator>&&|\|\||==|!=|<=|>=|[!<>()])|"
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_]{0,63}))"
)
_COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}


def validate_cel_expression(expression: str) -> bool:
    """Accept the small, side-effect-free CEL boolean surface Craft evaluates."""
    if not isinstance(expression, str):
        return False
    expression = expression.strip()
    if not expression or len(expression) > 1024:
        return False
    tokens = []
    offset = 0
    while offset < len(expression):
        match = _CEL_TOKEN.match(expression, offset)
        if not match:
            return False
        offset = match.end()
        tokens.append(next(value for value in match.groups() if value is not None))
    if not tokens:
        return False

    index = 0

    def accept(value):
        nonlocal index
        if index < len(tokens) and tokens[index] == value:
            index += 1
            return True
        return False

    def primary():
        nonlocal index
        if accept("("):
            valid = or_expression() and accept(")")
            return valid
        if index >= len(tokens):
            return False
        value = tokens[index]
        if value in {"true", "false", "null"} or value[0].isalpha() or value[0] == "_" or value[0].isdigit() or value[0] in {"'", '\"'}:
            index += 1
            return True
        return False

    def unary():
        return unary() if accept("!") else primary()

    def comparison():
        nonlocal index
        if not unary():
            return False
        if index < len(tokens) and tokens[index] in _COMPARISONS:
            index += 1
            return unary()
        return True

    def and_expression():
        if not comparison():
            return False
        while accept("&&"):
            if not comparison():
                return False
        return True

    def or_expression():
        if not and_expression():
            return False
        while accept("||"):
            if not and_expression():
                return False
        return True

    return or_expression() and index == len(tokens)


class RuleResult(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"  # context 字段缺失或表达式错误，无法判定


def check_rule(expression: str, context: dict) -> tuple[RuleResult, str | None]:
    """执行单条 CEL 表达式，返回 (RuleResult, error_message)。

    context: 纯 Python dict，key 为字段名，value 为 int/float/str/bool。
    """
    if not validate_cel_expression(expression):
        return RuleResult.SKIP, "表达式不在批准的 CEL 规则子集中"
    try:
        import celpy  # noqa: PLC0415
    except ImportError:
        return RuleResult.SKIP, "cel-python 未安装，请执行：pip install cel-python"

    try:
        env = celpy.Environment()
        ast = env.compile(expression)
        prog = env.program(ast)
        activation = celpy.json_to_cel(context)
        result = prog.evaluate(activation)
        return (RuleResult.PASS, None) if bool(result) else (RuleResult.FAIL, None)
    except Exception as e:
        msg = str(e)
        if any(kw in msg.lower() for kw in ("undeclared reference", "no such overload", "undefined")):
            return RuleResult.SKIP, f"context 字段缺失或类型不匹配: {msg}"
        _log.debug("CEL check_rule error | expr=%s | err=%s", expression, msg)
        return RuleResult.SKIP, f"表达式错误: {msg}"
