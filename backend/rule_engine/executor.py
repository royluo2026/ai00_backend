"""
backend/rule_engine/executor.py
────────────────────────────────
CEL 表达式执行器。返回四态结果：PASS / WARN / FAIL / SKIP。

依赖：cel-python（pip install cel-python），缺失时所有规则返回 SKIP。
"""
import logging
from enum import Enum

_log = logging.getLogger(__name__)


class RuleResult(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"  # context 字段缺失或表达式错误，无法判定


def check_rule(expression: str, context: dict) -> tuple[RuleResult, str | None]:
    """执行单条 CEL 表达式，返回 (RuleResult, error_message)。

    context: 纯 Python dict，key 为字段名，value 为 int/float/str/bool。
    """
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
