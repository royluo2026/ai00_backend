from __future__ import annotations
from ..domain.gbop import GbopRelease

class GbopService:
    def __init__(self): self.releases = {}
    def publish(self, release: GbopRelease):
        if not release.bop_commit_ref or not release.pbom_commit_ref or not release.ontology_release_ref:
            raise ValueError("exact BOP, PBOM and Ontology refs are required")
        self.releases[release.ref] = release
        return release

__all__ = ["GbopService"]
