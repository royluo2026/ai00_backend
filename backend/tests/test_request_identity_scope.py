from backend.platform_sdk.request_credentials import (
    authenticated_request_user,
    authenticated_user_scope,
)


def test_authenticated_user_scope_reuses_only_the_exact_request_actor():
    assert authenticated_request_user("user-1") is None
    with authenticated_user_scope({"gid": "user-1", "is_active": True}):
        assert authenticated_request_user("user-1") == {"gid": "user-1", "is_active": True}
        assert authenticated_request_user("user-2") is None
    assert authenticated_request_user("user-1") is None


def test_authenticated_user_scope_returns_a_copy():
    source = {"gid": "user-1", "is_active": True}
    with authenticated_user_scope(source):
        authenticated_request_user("user-1")["is_active"] = False
        assert authenticated_request_user("user-1")["is_active"] is True
