import pytest

import backend.plugin_platform.mounts as mounts
from backend.plugin_platform.mounts import MountTokenError, issue_mount_token, mount_url, verify_mount_token


def test_mount_token_binds_tenant_plugin_version_hash_and_expiry(monkeypatch):
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "test-secret-value-with-at-least-thirty-two-bytes")
    now = [1_800_000_000]
    monkeypatch.setattr(mounts.time, "time", lambda: now[0])
    token = issue_mount_token(tenant_gid="team-a", plugin_id="acme.ai00.hello", version="1.2.3", artifact_sha256="a" * 64, ttl_seconds=30)
    claims = verify_mount_token(token)
    assert (claims.tenant_gid, claims.plugin_id, claims.version, claims.artifact_sha256) == ("team-a", "acme.ai00.hello", "1.2.3", "a" * 64)
    assert token in mount_url(token, claims.plugin_id, claims.version, "assets/index.html")
    now[0] += 31
    with pytest.raises(MountTokenError): verify_mount_token(token)


def test_mount_token_tamper_and_short_secret_fail_closed(monkeypatch):
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "another-test-secret-with-at-least-thirty-two-bytes")
    token = issue_mount_token(tenant_gid="team-a", plugin_id="acme.ai00.hello", version="1.0.0", artifact_sha256="b" * 64)
    with pytest.raises(MountTokenError): verify_mount_token(token[:-1] + ("A" if token[-1] != "A" else "B"))
    monkeypatch.setenv("AI00_PLUGIN_MOUNT_SECRET", "short")
    with pytest.raises(MountTokenError): issue_mount_token(tenant_gid="team-a", plugin_id="acme.ai00.hello", version="1.0.0", artifact_sha256="b" * 64)
