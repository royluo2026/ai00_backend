"""Canonical Markdown and immutable OIS revision addressing."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"


@dataclass(frozen=True)
class PreparedMarkdownRevision:
    tenant_gid: str
    space_gid: str
    document_gid: str
    revision_gid: str
    markdown: str
    data: bytes
    sha256: str
    object_key: str
    media_type: str = MARKDOWN_MEDIA_TYPE


def _segment(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not _SEGMENT_RE.fullmatch(normalized):
        raise ValueError(f"{name} must be a safe 1-128 character identifier")
    return normalized


def canonical_markdown(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("markdown must be a string")
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def prepare_markdown_revision(
    *, tenant_gid: str, space_gid: str, document_gid: str, revision_gid: str, markdown: str,
) -> PreparedMarkdownRevision:
    tenant = _segment("tenant_gid", tenant_gid)
    space = _segment("space_gid", space_gid)
    document = _segment("document_gid", document_gid)
    revision = _segment("revision_gid", revision_gid)
    canonical = canonical_markdown(markdown)
    data = canonical.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    object_key = (
        f"knowledge/{tenant}/{space}/{document}/revisions/{revision}/"
        f"document.{digest}.md"
    )
    return PreparedMarkdownRevision(
        tenant_gid=tenant,
        space_gid=space,
        document_gid=document,
        revision_gid=revision,
        markdown=canonical,
        data=data,
        sha256=digest,
        object_key=object_key,
    )


def store_markdown_revision(prepared: PreparedMarkdownRevision) -> dict:
    from plugins.knowledge.knowledge_backend.storage import put_immutable

    result = put_immutable(prepared.object_key, prepared.data, prepared.media_type)
    if not result:
        raise RuntimeError("OIS is unavailable; Markdown revision was not persisted")
    if result.get("object_key") != prepared.object_key or result.get("sha256") != prepared.sha256:
        raise RuntimeError("OIS immutable revision verification failed")
    return result

def load_markdown_revision(object_key: str, expected_sha256: str) -> str:
    from plugins.knowledge.knowledge_backend.storage import get_immutable

    data = get_immutable(object_key, expected_sha256)
    if data is None:
        raise RuntimeError("OIS Markdown revision is unavailable or failed verification")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("OIS Markdown revision is not valid UTF-8") from exc
