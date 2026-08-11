"""Pytest plugin that emits exact mandatory-node outcomes for the strict runner."""
from __future__ import annotations

import json
import os
from pathlib import Path


_RESULTS: dict[str, str] = {}


def pytest_runtest_logreport(report):
    if report.when == "call":
        if getattr(report, "wasxfail", False):
            outcome = "xpassed" if report.passed else "xfailed"
        else:
            outcome = report.outcome
        _RESULTS[report.nodeid] = outcome
    elif report.when in {"setup", "teardown"} and (report.failed or report.skipped):
        _RESULTS[report.nodeid] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("AI00_ACCEPTANCE_RESULT_PATH", "").strip()
    if not target:
        return
    Path(target).write_text(
        json.dumps({"exit_status": int(exitstatus), "outcomes": _RESULTS}, sort_keys=True),
        encoding="utf-8", newline="\n",
    )
