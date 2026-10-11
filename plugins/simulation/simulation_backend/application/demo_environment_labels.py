"""Apply the configured demo display policy before export/package hashes exist."""
from dataclasses import replace
from backend.platform_sdk.demo_labels import demo_display_mapper
from ..domain.plmxml_environment_codec import EnvironmentModelDocument

def anonymous_runtime_model(model,user_gid):
    label=demo_display_mapper(user_gid)
    if label is None:return model
    documents=tuple(replace(document,display_name=label(document.display_name))
        if isinstance(document,EnvironmentModelDocument) else document for document in model.documents)
    hierarchies=tuple(replace(hierarchy,name=label(hierarchy.name),
        placements=tuple(replace(placement,name=label(placement.name)) for placement in hierarchy.placements))
        for hierarchy in model.hierarchies)
    return replace(model,documents=documents,hierarchies=hierarchies)

__all__=['anonymous_runtime_model']
