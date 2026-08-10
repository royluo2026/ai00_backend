import pytest

from backend.domain_ports.versioned_resources import VersionedResourceResolvers


def _resolver(reference, _context):
    return reference


def test_semantically_identical_provider_reload_is_idempotent():
    resolvers = VersionedResourceResolvers()
    reloaded = type(_resolver)(
        _resolver.__code__, _resolver.__globals__, _resolver.__name__,
        _resolver.__defaults__, _resolver.__closure__,
    )
    reloaded.__module__ = _resolver.__module__
    reloaded.__qualname__ = _resolver.__qualname__

    resolvers.register("craft.execution_plan", _resolver)
    resolvers.register("craft.execution_plan", reloaded)

    assert resolvers.resolve("craft.execution_plan", {"gid": "v1"}, None) == {"gid": "v1"}


def test_same_source_imported_through_package_alias_is_idempotent():
    resolvers = VersionedResourceResolvers()
    aliased = type(_resolver)(
        _resolver.__code__, _resolver.__globals__, _resolver.__name__,
        _resolver.__defaults__, _resolver.__closure__,
    )
    aliased.__module__ = "provider_distribution.capabilities"
    aliased.__qualname__ = _resolver.__qualname__

    resolvers.register("craft.execution_plan", _resolver)
    resolvers.register("craft.execution_plan", aliased)


def test_different_provider_cannot_take_over_registered_resource_type():
    resolvers = VersionedResourceResolvers()
    resolvers.register("craft.execution_plan", _resolver)

    with pytest.raises(RuntimeError, match="already registered"):
        resolvers.register("craft.execution_plan", lambda reference, _context: reference)
