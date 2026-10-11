"""Keep legacy Browser assets out of explicit backend deployment profiles."""
from pathlib import Path


def legacy_browser_dist(repository_root: Path, deployment_profile: str) -> Path | None:
    candidate = repository_root / "dist"
    return candidate if not deployment_profile and candidate.is_dir() else None
