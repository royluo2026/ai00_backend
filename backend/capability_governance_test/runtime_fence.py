"""Database serialization shared by governance writers and local artifact commit."""


def acquire_runtime_fence(cursor, *, required=False):
    # ponytail: one row serializes rare governance changes / local publications.
    # Split by version only if contention warrants a more complex lock ordering.
    try:
        cursor.execute("SELECT fence_id FROM workmanship_base_capability_runtime_fence WHERE fence_id=%s FOR UPDATE",(1,))
        row=cursor.fetchone()
    except Exception as exc:
        # Old installations may still perform governance writes before migration;
        # local side effects require the fence and therefore remain fail-closed.
        if not required and getattr(exc,'args',())[0:1]==(1146,):
            return False
        raise
    if row is None and required:
        raise RuntimeError('local_provider_governance_fence_unavailable')
    return row is not None
