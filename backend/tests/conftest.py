"""Global pytest safety defaults.

Live database verification is opt-in so importing the FastAPI app during unit
test collection can never inherit desktop-saved OceanBase credentials.
"""
from __future__ import annotations

import os


if os.environ.get("AI00_ALLOW_LIVE_DB_TESTS") != "1":
    os.environ["AI00_PYTEST_OFFLINE"] = "1"
    for variable in (
        "AI00_CRAFT_DB_URL",
        "AI00_AGENT_DB_URL",
        "AI00_SIMULATION_DB_URL",
        "AI00_DEVICE_DB_URL",
        "AI00_PROJECT_MANAGEMENT_DB_URL",
        "AI00_KNOWLEDGE_DB_URL",
        "AI00_DDL_DB_URL",
    ):
        os.environ.pop(variable, None)
