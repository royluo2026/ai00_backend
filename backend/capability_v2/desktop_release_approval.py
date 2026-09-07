"""Verify technical App approvals independently of Capability human decisions.

No signing endpoint or approval writer is supplied here. Trusted release
authority and current role/revocation resolvers belong to the server workflow;
the candidate record can neither select trust roots nor lower the threshold.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import re
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, ValidationError, model_validator

from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
from .contracts import FrozenModel, IDENTITY_PATTERN


class ReleaseApprovalError(ValueError):
    pass


class ReleaseSignature(FrozenModel):
    reviewer_id: str = Field(pattern=IDENTITY_PATTERN)
    key_id: str = Field(pattern=IDENTITY_PATTERN)
    signature: str = Field(min_length=1, max_length=256)


class DesktopReleaseApproval(FrozenModel):
    approval_id: str = Field(pattern=IDENTITY_PATTERN)
    release_id: str = Field(pattern=IDENTITY_PATTERN)
    author_id: str = Field(pattern=IDENTITY_PATTERN)
    artifact_hashes: dict[str, str]
    approved_at: datetime
    expires_at: datetime
    signatures: tuple[ReleaseSignature, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def immutable_artifacts_and_times(self):
        if not self.artifact_hashes or len(self.artifact_hashes) > 4096 or any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,511}", name)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            for name, digest in self.artifact_hashes.items()
        ):
            raise ValueError("immutable_artifact_hashes_required")
        if any(value.utcoffset() is None for value in (self.approved_at, self.expires_at)):
            raise ValueError("timezone_required")
        if self.expires_at <= self.approved_at:
            raise ValueError("approval_expiry_invalid")
        return self


class DesktopReleaseVerification(FrozenModel):
    approval_id: str
    release_id: str
    approval_hash: str
    reviewers: tuple[str, ...]
    expires_at: datetime
    technical_release_approved: bool = True


class DesktopReleaseApprovalService:
    def __init__(self, *, key_resolver, role_resolver, is_revoked,
                 signature_threshold: int, clock=lambda: datetime.now(UTC)):
        if type(signature_threshold) is not int or not 1 <= signature_threshold <= 32:
            raise ValueError("signature_threshold_invalid")
        self._key_resolver = key_resolver
        self._role_resolver = role_resolver
        self._is_revoked = is_revoked
        self._threshold = signature_threshold
        self._clock = clock

    def verify(self, record: Mapping, *, expected_release_id: str,
               expected_artifact_hashes: Mapping[str, str]) -> DesktopReleaseVerification:
        try:
            # Validate original input and sign its exact canonical wire values.
            # Revalidation also prevents model_copy/model_construct bypasses.
            raw = deepcopy(dict(record))
            approval = DesktopReleaseApproval.model_validate(raw)
            now = self._clock()
            if not approval.approved_at <= now < approval.expires_at:
                raise ReleaseApprovalError("approval_expired_or_future")
            if (approval.release_id != expected_release_id or
                    approval.artifact_hashes != dict(expected_artifact_hashes)):
                raise ReleaseApprovalError("release_artifact_binding_mismatch")
            if self._is_revoked(approval.approval_id) is not False:
                raise ReleaseApprovalError("approval_revoked_or_unavailable")
            body = {k: v for k, v in raw.items() if k != "signatures"}
            reviewers = set()
            for signature in approval.signatures:
                reviewer = signature.reviewer_id
                if reviewer == approval.author_id:
                    raise ReleaseApprovalError("separation_of_duties")
                if reviewer in reviewers:
                    raise ReleaseApprovalError("duplicate_reviewer")
                if "desktop_release_approver" not in self._role_resolver(reviewer):
                    raise ReleaseApprovalError("desktop_release_approver_required")
                key = self._key_resolver(signature.key_id)
                if (not key or key.get("purpose") != "desktop_release_authority" or
                        key.get("revoked") is not False or
                        not key["not_before"] <= approval.approved_at <= now < key["not_after"] or
                        not isinstance(key.get("public_key"), Ed25519PublicKey)):
                    raise ReleaseApprovalError("release_authority_key_inactive")
                data = canonicalize_v2(dict(protocol="ai00.desktop.release-approval.v1", approval=body,
                    reviewer_id=reviewer, key_id=signature.key_id))
                encoded = signature.signature
                decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
                if len(decoded) != 64 or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode() != encoded:
                    raise ReleaseApprovalError("approval_signature_invalid")
                key["public_key"].verify(decoded, data)
                reviewers.add(reviewer)
            if len(reviewers) < self._threshold:
                raise ReleaseApprovalError("signature_threshold_not_met")
            return DesktopReleaseVerification(approval_id=approval.approval_id, release_id=approval.release_id,
                approval_hash="sha256:" + hashlib.sha256(canonicalize_v2(raw)).hexdigest(),
                reviewers=tuple(sorted(reviewers)), expires_at=approval.expires_at)
        except ReleaseApprovalError:
            raise
        except (ValidationError, InvalidSignature, ValueError, TypeError, KeyError) as exc:
            raise ReleaseApprovalError("release_approval_invalid") from exc
