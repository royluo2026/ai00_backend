"""Shared validation for independently owned domain connection-pool budgets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DomainPoolDefault:
    env_prefix: str
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class DomainPoolLimits:
    domain: str
    env_prefix: str
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class AggregatePoolBudget:
    domains: tuple[DomainPoolLimits, ...]
    workers: int
    per_worker_max_connections: int
    total_max_connections: int
    deployment_ceiling: int


DOMAIN_POOL_DEFAULTS: dict[str, DomainPoolDefault] = {
    "base": DomainPoolDefault("AI00_BASE", 2, 20),
    "agent": DomainPoolDefault("AI00_AGENT", 1, 10),
    "craft": DomainPoolDefault("AI00_CRAFT", 1, 20),
    "device": DomainPoolDefault("AI00_DEVICE", 1, 10),
    "digital_model": DomainPoolDefault("AI00_DIGITAL_MODEL", 1, 20),
    "factory": DomainPoolDefault("AI00_FACTORY", 1, 20),
    "integration": DomainPoolDefault("AI00_INTEGRATION", 1, 10),
    "knowledge": DomainPoolDefault("AI00_KNOWLEDGE", 1, 20),
    "ontology": DomainPoolDefault("AI00_ONTOLOGY", 1, 20),
    "project_management": DomainPoolDefault("AI00_PROJECT_MANAGEMENT", 1, 20),
    "simulation": DomainPoolDefault("AI00_SIMULATION", 1, 10),
}


def _positive_int(raw: str, name: str, *, upper: int = 10_000) -> int:
    try:
        value = int(raw.strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1 or value > upper:
        raise ValueError(f"{name} must be between 1 and {upper}")
    return value


def pool_limits(domain: str, *, environ: Mapping[str, str] | None = None) -> DomainPoolLimits:
    source = os.environ if environ is None else environ
    try:
        default = DOMAIN_POOL_DEFAULTS[domain]
    except KeyError as exc:
        raise ValueError(f"unknown domain: {domain}") from exc
    min_name = f"{default.env_prefix}_DB_POOL_MIN"
    max_name = f"{default.env_prefix}_DB_POOL_MAX"
    minimum = _positive_int(source.get(min_name, str(default.minimum)), min_name, upper=500)
    maximum = _positive_int(source.get(max_name, str(default.maximum)), max_name, upper=500)
    if minimum > maximum:
        raise ValueError(f"{domain} pool minimum cannot exceed maximum")
    return DomainPoolLimits(domain, default.env_prefix, minimum, maximum)


def validate_aggregate_pool_budget(
    *, environ: Mapping[str, str] | None = None,
) -> AggregatePoolBudget:
    source = os.environ if environ is None else environ
    workers = _positive_int(source.get("AI00_WEB_WORKERS", "1"), "AI00_WEB_WORKERS", upper=64)
    ceiling = _positive_int(
        source.get("AI00_DB_POOL_TOTAL_MAX", "180"), "AI00_DB_POOL_TOTAL_MAX", upper=10_000,
    )
    domains = tuple(pool_limits(name, environ=source) for name in DOMAIN_POOL_DEFAULTS)
    per_worker = sum(item.maximum for item in domains)
    total = per_worker * workers
    if total > ceiling:
        raise ValueError(
            f"aggregate domain pool maximum {total} exceeds deployment ceiling {ceiling}"
        )
    return AggregatePoolBudget(domains, workers, per_worker, total, ceiling)


__all__ = [
    "AggregatePoolBudget", "DOMAIN_POOL_DEFAULTS", "DomainPoolDefault",
    "DomainPoolLimits", "pool_limits", "validate_aggregate_pool_budget",
]
