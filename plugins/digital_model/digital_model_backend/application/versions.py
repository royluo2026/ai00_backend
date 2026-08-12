class ModelVersionService:
    def __init__(self, versions=()): self.versions = {v.ref: v for v in versions}
    def replace_component(self, version_ref, component_ref):
        changed = self.versions[version_ref].replace_component(component_ref)
        self.versions[version_ref] = changed
        return changed
