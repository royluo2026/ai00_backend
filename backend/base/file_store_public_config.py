"""Governed, read-only public projection of runtime file-store configuration."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.contracts import ExposurePolicy
from backend.capability_v2.provider_contracts import CapabilitySpec
from backend.platform_sdk import file_store_config

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
from .provider import descriptor_for


PUBLIC_CONFIG_CAPABILITY_ID = "base.file_store.public_config.get"


def _mask(value: Any) -> str:
    text = str(value or "")
    if len(text) > 8:
        return text[:4] + "••••" + text[-4:]
    return "•" * len(text)


def public_file_store_config(_payload: dict[str, Any], context: object) -> dict[str, Any]:
    raw = file_store_config.read_runtime_file_store_config()
    roles = {str(role) for role in getattr(context, "active_roles", ())}
    is_admin = bool(roles & {"super_admin", "team_admin"})
    ois = raw.get("ois") if isinstance(raw.get("ois"), dict) else {}
    result: dict[str, Any] = {
        "success": True,
        "source": str(raw.get("source") or "none"),
        "has_creds": bool(raw.get("access_key") and raw.get("secret_key")),
        "is_admin": is_admin,
        "ois_enabled": bool(ois.get("identify")),
        "ois_source": str(raw.get("ois_source") or "none"),
    }
    if is_admin:
        result.update({
            "endpoint": str(raw.get("endpoint") or ""),
            "bucket": str(raw.get("bucket") or "ai00"),
            "public_url": str(raw.get("public_url") or ""),
            "key_preview": _mask(raw.get("access_key")),
            "ois": {
                "identify": str(ois.get("identify") or ""),
                "env": str(ois.get("env") or ""),
                "ois3_url": str(ois.get("ois3_url") or ois.get("api_base") or ""),
                "region": str(ois.get("region") or ""),
                "licloud_appid": str(ois.get("licloud_appid") or ""),
                "idaas_url": str(ois.get("idaas_url") or ""),
                "idaas_client_id": str(ois.get("idaas_client_id") or ""),
                "idaas_service_id": str(ois.get("idaas_service_id") or ""),
                "public_base_url": str(ois.get("public_base_url") or ""),
                "secret_preview": _mask(ois.get("idaas_client_secret")),
            },
        })
    return result


def register_file_store_public_config_capability(registry: Any) -> None:
    spec = CapabilitySpec(
        id=PUBLIC_CONFIG_CAPABILITY_ID,
        owner="base",
        description="Read the secret-filtered public file-store runtime configuration.",
        use_when="An authenticated web client needs file-store feature availability or administrator-safe display values.",
        do_not_use_when="A caller needs raw storage credentials or intends to mutate configuration.",
        risk="read",
        confirmation="none",
        idempotent=True,
        permissions=(),
        plugin_callable=False,
        input_schema=INPUT_SCHEMAS[PUBLIC_CONFIG_CAPABILITY_ID],
        output_schema=OUTPUT_SCHEMAS[PUBLIC_CONFIG_CAPABILITY_ID],
        tags=("base", "file-store", "configuration", "public-projection"),
    )
    descriptor = descriptor_for(spec).model_copy(update={
        "exposure": ExposurePolicy(web=True, api=True, plugin=False, agent=False, mcp=False),
        "agent_output_schema": None,
        "delegation_policy": "none",
        "data_classification": "confidential",
    })
    registry.register(spec, public_file_store_config, descriptor=descriptor)


__all__ = [
    "PUBLIC_CONFIG_CAPABILITY_ID",
    "public_file_store_config",
    "register_file_store_public_config_capability",
]
