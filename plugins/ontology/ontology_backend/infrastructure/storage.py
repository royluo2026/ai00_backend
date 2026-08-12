from backend.capability_v2.artifacts import OisImmutableObjectStorage

_store = OisImmutableObjectStorage()

def put_immutable(object_key, data, media_type):
    return _store.put_immutable(object_key, data, media_type)

