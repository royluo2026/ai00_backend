"""Real signatures test independent technical release approval; no human evidence is minted."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.contracts.connector_execution_plan_v2 import canonicalize_v2

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)
ARTIFACTS = {"installer": "sha256:" + "a" * 64, "impact_closure": "sha256:" + "b" * 64}


def make_approval():
    assert find_spec("backend.capability_v2.desktop_release_approval") is not None, "technical release verifier missing"
    from backend.capability_v2.desktop_release_approval import DesktopReleaseApprovalService, ReleaseApprovalError
    key = Ed25519PrivateKey.generate()
    key_record = dict(public_key=key.public_key(), purpose="desktop_release_authority", revoked=False,
        not_before=NOW-timedelta(days=1), not_after=NOW+timedelta(days=1))
    roles = {"reviewer-1": {"desktop_release_approver"}, "reviewer-2": {"desktop_release_approver"}, "author": {"desktop_release_approver"}}
    revoked = set()
    service = DesktopReleaseApprovalService(key_resolver=lambda _: key_record, role_resolver=lambda user: roles.get(user, set()),
        is_revoked=lambda approval_id: approval_id in revoked, signature_threshold=2, clock=lambda: NOW)
    record = dict(approval_id="approval-1", release_id="desktop-1", author_id="author", artifact_hashes=ARTIFACTS.copy(),
        approved_at=NOW.isoformat(), expires_at=(NOW+timedelta(hours=1)).isoformat(), signatures=[])
    def sign(record, reviewers=("reviewer-1", "reviewer-2")):
        record = deepcopy(record)
        record["signatures"] = []
        body = {k: v for k, v in record.items() if k != "signatures"}
        for reviewer in reviewers:
            binding = dict(reviewer_id=reviewer, key_id="authority-1")
            data = canonicalize_v2(dict(protocol="ai00.desktop.release-approval.v1", approval=body, **binding))
            record["signatures"].append(dict(**binding, signature=base64.urlsafe_b64encode(key.sign(data)).rstrip(b"=").decode()))
        return record
    return service, ReleaseApprovalError, record, sign, key_record, roles, revoked


def verify(fixture, record):
    return fixture[0].verify(record, expected_release_id="desktop-1", expected_artifact_hashes=ARTIFACTS)


def test_valid_technical_approval_is_independent_and_does_not_mutate_evidence():
    approval = make_approval()
    record = approval[3](approval[2])
    original = deepcopy(record)
    result = verify(approval, record)
    assert result.technical_release_approved is True
    assert not hasattr(result, "human_approved")
    assert not hasattr(result, "runtime_verified")
    assert record == original


def test_release_author_cannot_approve_own_artifacts():
    approval = make_approval()
    with pytest.raises(approval[1], match="separation_of_duties"):
        verify(approval, approval[3](approval[2], ("author", "reviewer-1")))


@pytest.mark.parametrize("reviewers", [("reviewer-1",), ("reviewer-1", "reviewer-1")])
def test_threshold_requires_distinct_authorized_reviewers(reviewers):
    approval = make_approval()
    with pytest.raises(approval[1], match="signature_threshold|duplicate_reviewer"):
        verify(approval, approval[3](approval[2], reviewers))


@pytest.mark.parametrize("field,value", [("release_id", "other"), ("author_id", "other"),
    ("artifact_hashes", {"installer": "sha256:" + "c" * 64}), ("expires_at", (NOW+timedelta(days=5)).isoformat())])
def test_mutating_any_signed_release_binding_is_rejected(field, value):
    approval = make_approval()
    record = approval[3](approval[2])
    record[field] = value
    with pytest.raises(approval[1]):
        verify(approval, record)


@pytest.mark.parametrize("change", ["role", "key", "approval", "purpose", "key_expired", "key_future"])
def test_current_roles_authority_keys_and_revocations_are_reread(change):
    approval = make_approval()
    record = approval[3](approval[2])
    assert verify(approval, record).technical_release_approved
    if change == "role": approval[5]["reviewer-1"].clear()
    elif change == "key": approval[4]["revoked"] = True
    elif change == "approval": approval[6].add("approval-1")
    elif change == "purpose": approval[4]["purpose"] = "capability_business_approval"
    elif change == "key_expired": approval[4]["not_after"] = NOW
    else: approval[4]["not_before"] = NOW + timedelta(seconds=1)
    with pytest.raises(approval[1]): verify(approval, record)


@pytest.mark.parametrize("field,value", [("expires_at", NOW.isoformat()),
    ("approved_at", (NOW+timedelta(seconds=1)).isoformat()), ("approved_at", "2026-09-07T12:00:00"),
    ("human_approved", True), ("artifact_hashes", {}), ("artifact_hashes", {"installer": "latest"})])
def test_invalid_or_forged_approval_metadata_fails_closed(field, value):
    approval = make_approval()
    record = deepcopy(approval[2]); record[field] = value
    with pytest.raises(approval[1]): verify(approval, approval[3](record))


def test_unknown_authority_and_bad_signature_fail_closed():
    approval = make_approval()
    record = approval[3](approval[2])
    record["signatures"][0]["signature"] = "invalid"
    with pytest.raises(approval[1]): verify(approval, record)
    approval[4]["public_key"] = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(approval[1]): verify(approval, approval[3](approval[2]))


@pytest.mark.parametrize("threshold", [0, -1, True, 1.5])
def test_signature_threshold_cannot_be_disabled(threshold):
    approval = make_approval()
    cls = type(approval[0])
    with pytest.raises(ValueError):
        cls(key_resolver=lambda _: None, role_resolver=lambda _: (), is_revoked=lambda _: False, signature_threshold=threshold)


def test_record_is_snapshotted_before_current_authority_lookups():
    approval = make_approval()
    record = approval[3](approval[2])
    def roles(user):
        # Caller memory may change while a remote role lookup is in progress.
        record["artifact_hashes"]["installer"] = "sha256:" + "c" * 64
        return approval[5][user]
    service = type(approval[0])(key_resolver=lambda _: approval[4], role_resolver=roles,
        is_revoked=lambda _: False, signature_threshold=2, clock=lambda: NOW)
    assert service.verify(record, expected_release_id="desktop-1", expected_artifact_hashes=ARTIFACTS).technical_release_approved


def test_unknown_authority_id_cannot_select_request_supplied_key():
    approval = make_approval()
    record = approval[3](approval[2])
    service = type(approval[0])(key_resolver=lambda _: None, role_resolver=lambda user: approval[5][user],
        is_revoked=lambda _: False, signature_threshold=2, clock=lambda: NOW)
    with pytest.raises(approval[1], match="release_authority_key_inactive"):
        service.verify(record, expected_release_id="desktop-1", expected_artifact_hashes=ARTIFACTS)
