import hashlib
import pytest
from plugins.knowledge.knowledge_backend import storage


@pytest.fixture(autouse=True)
def restore_store():
    previous = storage._store
    yield
    storage.configure_object_store(previous)


class Store:
    def __init__(self): self.calls = []; self.data = b'body'
    def get_immutable(self, key, digest):
        self.calls.append((key, digest))
        return self.data


def test_cache_is_bound_to_object_and_verified_version_hash():
    store = Store(); storage.configure_object_store(store)
    digest = hashlib.sha256(store.data).hexdigest()
    assert storage.get_immutable('tenant-a/doc', digest) == b'body'
    storage.get_immutable('tenant-a/doc', digest)
    assert len(store.calls) == 1
    storage.get_immutable('tenant-b/doc', digest)
    store.data = b'new version'
    storage.get_immutable('tenant-a/doc', hashlib.sha256(store.data).hexdigest())
    assert len(store.calls) == 3


def test_unavailable_content_is_retried_and_store_reconfiguration_clears_cache():
    store = Store(); storage.configure_object_store(store)
    digest = hashlib.sha256(b'body').hexdigest()
    store.data = None
    assert storage.get_immutable('doc', digest) is None
    store.data = b'body'
    assert storage.get_immutable('doc', digest) == b'body'
    assert len(store.calls) == 2
    replacement = Store(); storage.configure_object_store(replacement)
    storage.get_immutable('doc', digest)
    assert len(replacement.calls) == 1


def test_cache_eviction_bounds_total_memory(monkeypatch):
    monkeypatch.setattr(storage, '_CACHE_MAX_BYTES', 6)
    store = Store(); storage.configure_object_store(store)
    digest = hashlib.sha256(store.data).hexdigest()
    storage.get_immutable('a', digest)
    storage.get_immutable('b', digest)
    storage.get_immutable('a', digest)
    assert len(store.calls) == 3
    assert storage._cache_bytes <= 6
