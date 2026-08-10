from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_external_consumers_are_owned_by_the_backend_repository():
    required = (
        "services/agent-runtime/package.json",
        "services/agent-runtime/src/server.ts",
        "services/mcp-gateway/package.json",
        "services/mcp-gateway/src/server.ts",
        "local-runtime/Ai00.LocalRuntime.sln",
        "local-runtime/src/Ai00.LocalRuntime.Contracts/Contracts.cs",
    )

    missing = [path for path in required if not (REPO_ROOT / path).is_file()]

    assert missing == []


def test_service_ci_builds_each_owned_runtime():
    workflow = REPO_ROOT / ".github/workflows/capability-v2-services.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "working-directory: services/agent-runtime" in text
    assert "working-directory: services/mcp-gateway" in text
    assert "dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release" in text
