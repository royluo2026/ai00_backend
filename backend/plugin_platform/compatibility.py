"""Small, deterministic SemVer range evaluator for platform compatibility gates."""
from __future__ import annotations
import re

class CompatibilityError(ValueError): pass

def _version(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if not match: raise CompatibilityError(f"invalid SemVer: {value}")
    return tuple(int(part) for part in match.groups())

def satisfies(version: str, expression: str) -> bool:
    current, clauses = _version(version), expression.split()
    if not clauses: raise CompatibilityError("empty compatibility range")
    for clause in clauses:
        match = re.fullmatch(r"(>=|<=|>|<|=|\^|~)?(\d+\.\d+\.\d+)", clause)
        if not match: raise CompatibilityError(f"unsupported compatibility clause: {clause}")
        op, wanted = match.group(1) or "=", _version(match.group(2))
        if op == ">=" and not current >= wanted: return False
        if op == "<=" and not current <= wanted: return False
        if op == ">" and not current > wanted: return False
        if op == "<" and not current < wanted: return False
        if op == "=" and not current == wanted: return False
        if op == "^" and not (current >= wanted and current < (wanted[0] + 1, 0, 0)): return False
        if op == "~" and not (current >= wanted and current < (wanted[0], wanted[1] + 1, 0)): return False
    return True
