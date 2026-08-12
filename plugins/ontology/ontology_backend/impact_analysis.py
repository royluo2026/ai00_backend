"""Fail-closed release impact analysis across independently maintained domains."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import threading

from backend.capability_v2.revision.models import Change
from backend.domain_ports.ontology import ImpactReference, ImpactReport, OntologyImpactProvider


REQUIRED_PROVIDERS = ("agent", "craft", "digital_model", "plugins")


class StaticImpactProvider:
    """Deterministic provider for tests and reviewed generated reference catalogs."""

    def __init__(self, name: str, references: tuple[ImpactReference, ...]) -> None:
        if name not in REQUIRED_PROVIDERS:
            raise ValueError("unsupported ontology impact provider")
        self.name = name
        self._references = references

    def references(self, ontology_object_ids: Sequence[str]) -> tuple[ImpactReference, ...]:
        selected = set(ontology_object_ids)
        return tuple(item for item in self._references if item.ontology_object_id in selected)


class ImpactAnalysisService:
    def __init__(self, providers: Mapping[str, OntologyImpactProvider]) -> None:
        unknown = sorted(set(providers) - set(REQUIRED_PROVIDERS))
        if unknown:
            raise ValueError(f"unsupported ontology impact providers: {', '.join(unknown)}")
        self._providers = dict(providers)

    def analyze(self, changes: Sequence[Change]) -> ImpactReport:
        breaking_ids = tuple(sorted({
            item.identity for item in changes if item.breaking and item.identity is not None
        }))
        if not breaking_ids:
            return ImpactReport(activation_allowed=True)
        missing = tuple(sorted(set(REQUIRED_PROVIDERS) - set(self._providers)))
        references: list[ImpactReference] = []
        failed: list[str] = []
        for name in REQUIRED_PROVIDERS:
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                rows = provider.references(breaking_ids)
            except Exception:
                failed.append(name)
                continue
            if any(item.provider != name for item in rows):
                failed.append(name)
                continue
            references.extend(rows)
        unavailable = tuple(sorted(set(missing) | set(failed)))
        unresolved = tuple(sorted(
            (item for item in references if item.status == "unresolved"),
            key=lambda item: (item.provider, item.consumer_id, item.ontology_object_id),
        ))
        return ImpactReport(
            activation_allowed=not unavailable and not unresolved,
            breaking_object_ids=breaking_ids,
            unresolved=unresolved,
            missing_providers=unavailable,
        )


class ImpactProviderRegistry:
    """Startup-only registry for official domain-owned impact providers."""

    def __init__(self) -> None:
        self._providers: dict[str, OntologyImpactProvider] = {}
        self._frozen = False
        self._lock = threading.Lock()

    def register(self, provider: OntologyImpactProvider) -> None:
        if provider.name not in REQUIRED_PROVIDERS:
            raise ValueError("unsupported ontology impact provider")
        with self._lock:
            if self._frozen:
                raise RuntimeError("ontology impact provider registry is frozen")
            if provider.name in self._providers:
                raise ValueError(f"duplicate ontology impact provider: {provider.name}")
            self._providers[provider.name] = provider

    def service(self) -> ImpactAnalysisService:
        with self._lock:
            self._frozen = True
            providers = dict(self._providers)
        return ImpactAnalysisService(providers)


official_impact_providers = ImpactProviderRegistry()
