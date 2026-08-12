from dataclasses import dataclass, replace

class ImmutableVersionError(ValueError): pass

@dataclass(frozen=True)
class ModelVersion:
    ref: str
    artifact_ref: str
    project_ref: str
    published: bool
    components: tuple[str, ...]
    def replace_component(self, component_ref):
        if self.published: raise ImmutableVersionError(self.ref)
        return replace(self, components=(*self.components, component_ref))
