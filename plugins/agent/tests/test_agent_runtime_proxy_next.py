from plugins.agent.agent_backend.routers import agent_runtime_proxy_next as proxy


def test_pi_proxy_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("AI00_AGENT_RUNTIME_MODE", raising=False)
    assert proxy.enabled() is False


def test_explicit_pi_proxy_remains_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AI00_AGENT_RUNTIME_MODE", "pi")
    assert proxy.enabled() is True
