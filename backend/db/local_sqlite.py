"""Retired compatibility module.

Private annotations moved to Base-owned OceanBase storage. Existing local SQLite
files are not opened or mutated by the application runtime.
"""


def get_local_db():
    raise RuntimeError("local annotation SQLite is retired; use /api/self_ann backed by OceanBase")
