"""Versioned, non-executable business workspace contracts owned by Agent."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ImplementationOption(Closed):
    kind: Literal['unset','human','program','agent'] = 'unset'
    label: str = Field(default='',max_length=128)
    status: Literal['not_started','developing','active','retired'] = 'not_started'
    llm: bool = False
    skill_gid: str | None = None
    skill_version: str | None = None
    source_item_gids: list[str] = Field(default_factory=list, max_length=100)


class Implementation(ImplementationOption):
    alternatives: list[ImplementationOption] = Field(default_factory=list,max_length=16)
    coordination: Literal['single','parallel','transition','human_review'] = 'single'


SemanticType = Literal['target','decision','action','object','measurement','compare','disturbance','uncertainty']
RelationType = Literal['sequence','data','control','measurement','feedback','feedforward','disturbance','association']


class Scope(Closed):
    gid: str = Field(min_length=1,max_length=128)
    title: str = Field(min_length=1,max_length=255)
    parent_gid: str | None = None
    business_node_gid: str | None = None


class Axis(Closed):
    x_items: list[str] = Field(min_length=0,max_length=64)
    y_items: list[str] = Field(min_length=1,max_length=64)
    column_width: int = Field(default=230,ge=180,le=600)
    row_height: int = Field(default=150,ge=120,le=600)

    @model_validator(mode='after')
    def unique_labels(self):
        for values in (self.x_items,self.y_items):
            if len(values)!=len(set(values)) or any(not value.strip() or len(value)>128 for value in values):
                raise ValueError('axis labels must be unique and nonempty')
        return self


class Placement(Closed):
    node_gid: str
    x_item_key: str
    y_item_key: str
    slot_x: int | None = Field(default=None,ge=-1000,le=1000)
    slot_y: int | None = Field(default=None,ge=-1000,le=1000)

    @model_validator(mode='after')
    def paired_slots(self):
        if (self.slot_x is None)!=(self.slot_y is None): raise ValueError('both local slot coordinates required')
        return self


class View(Closed):
    gid: str
    view_type: Literal['org','task']
    axis_mode: Literal['inherited','independent','overview'] = 'inherited'
    scope_gid: str | None = None
    task_gid: str | None = None
    axis: Axis
    placements: list[Placement] = Field(default_factory=list,max_length=500)


class NodeOverride(Closed):
    title: str | None = None
    semantic_type: SemanticType | None = None
    implementation: Implementation | None = None
    objective: str | None = None
    inputs: list[dict[str,Any]] | None = None
    outputs: list[dict[str,Any]] | None = None


class Variant(Closed):
    gid: str
    task_gid: str
    stage_ref: str = Field(min_length=1,max_length=128)
    vehicle_ref: str | None = None
    version: str = '1'
    base_version: str | None = None
    data_snapshot_ref: str | None = None
    active_node_gids: list[str] | None = Field(default=None, max_length=500)
    node_overrides: dict[str,NodeOverride] = Field(default_factory=dict)


class WorkspaceDefinition(Closed):
    schema_version: Literal[1] = 1
    scopes: list[Scope] = Field(default_factory=list,max_length=500)
    tasks: list[Scope] = Field(default_factory=list,max_length=500)
    views: list[View] = Field(default_factory=list,max_length=1000)
    variants: list[Variant] = Field(default_factory=list,max_length=1000)
    stages: list[str] = Field(default_factory=list,max_length=64)

    @model_validator(mode='after')
    def relationships(self):
        for entries in (self.scopes,self.tasks):
            by_id={item.gid:item for item in entries}
            if len(by_id)!=len(entries): raise ValueError('duplicate hierarchy gid')
            for item in entries:
                seen=set(); current=item
                while current:
                    if current.gid in seen or len(seen)>=32: raise ValueError('hierarchy cycle or excessive depth')
                    seen.add(current.gid)
                    if current.parent_gid and current.parent_gid not in by_id: raise ValueError('missing hierarchy parent')
                    current=by_id.get(current.parent_gid)
        scopes={s.gid for s in self.scopes}; tasks={t.gid for t in self.tasks}
        if len({v.gid for v in self.views})!=len(self.views): raise ValueError('duplicate view gid')
        identities=set()
        for view in self.views:
            key=(view.view_type,view.scope_gid,view.task_gid)
            if key in identities: raise ValueError('duplicate view identity')
            identities.add(key)
            if view.view_type=='org' and (view.scope_gid not in scopes or view.task_gid): raise ValueError('invalid org view')
            if view.view_type=='task' and (view.task_gid not in tasks or view.scope_gid): raise ValueError('invalid task view')
            if len({p.node_gid for p in view.placements})!=len(view.placements): raise ValueError('duplicate placement')
            slots=[(p.x_item_key,p.y_item_key,p.slot_x,p.slot_y) for p in view.placements if p.slot_x is not None]
            if len(slots)!=len(set(slots)): raise ValueError('duplicate local slot')
            if view.axis_mode=='overview':
                if view.view_type!='org' or view.axis.x_items: raise ValueError('overview must be an org view without horizontal stages')
            elif not view.axis.x_items: raise ValueError('horizontal axis required')
            xs=['总览'] if view.axis_mode=='overview' else view.axis.x_items
            if any(p.x_item_key not in xs or p.y_item_key not in view.axis.y_items for p in view.placements): raise ValueError('placement outside axis')
        if len({v.gid for v in self.variants})!=len(self.variants): raise ValueError('duplicate variant')
        for variant in self.variants:
            if variant.task_gid not in tasks: raise ValueError('variant task missing')
        return self


def validate_workspace(graph):
    node_ids={n.gid for n in graph.nodes}
    items={i.gid for i in graph.items}
    for node in graph.nodes:
        if any(gid not in items for implementation in [node.implementation,*node.implementation.alternatives]
               for gid in implementation.source_item_gids): raise ValueError('implementation item missing')
        for ports in (node.inputs,node.outputs):
            keys=[p['key'] for p in ports if p.get('key')]
            if len(keys)!=len(set(keys)): raise ValueError('duplicate port key')
    if graph.workspace:
        scopes={s.gid for s in graph.workspace.scopes}
        by_node={n.gid:n for n in graph.nodes}
        for scope in graph.workspace.scopes:
            if scope.business_node_gid:
                node=by_node.get(scope.business_node_gid)
                if not node or node.level!=1: raise ValueError('business scope must link to an L1 card')
        for node in graph.nodes:
            if node.home_scope_gid is not None and node.home_scope_gid not in scopes: raise ValueError('node scope missing')
        for view in graph.workspace.views:
            for p in view.placements:
                if p.node_gid not in node_ids: raise ValueError('placement node missing')
                node=next(n for n in graph.nodes if n.gid==p.node_gid)
                if view.view_type=='org' and node.home_scope_gid!=view.scope_gid: raise ValueError('org placement outside home scope')
        for variant in graph.workspace.variants:
            available={p.node_gid for v in graph.workspace.views if v.task_gid==variant.task_gid for p in v.placements}
            if not set(variant.node_overrides).issubset(available) or (variant.active_node_gids is not None and not set(variant.active_node_gids).issubset(available)): raise ValueError('variant node outside task')
            inactive = available - set(variant.active_node_gids) if variant.active_node_gids is not None else set()
            effective_nodes=[]
            for node in graph.nodes:
                if node.gid in inactive: continue
                override=variant.node_overrides.get(node.gid)
                data=node.model_dump()
                if override: data.update(override.model_dump(exclude_none=True))
                effective_nodes.append(type(node).model_validate(data))
            effective_ids={node.gid for node in effective_nodes}
            effective=graph.model_copy(update={
                'workspace':None,'nodes':effective_nodes,
                'edges':[edge for edge in graph.edges if edge.source_node_gid in effective_ids and edge.target_node_gid in effective_ids],
            })
            validate_workspace(effective)
    nodes={n.gid:n for n in graph.nodes}
    for edge in graph.edges:
        if bool(edge.source_port_key)!=bool(edge.target_port_key): raise ValueError('both port endpoints required')
        if edge.source_port_key:
            source=next((p for p in nodes[edge.source_node_gid].outputs if p.get('key')==edge.source_port_key),None)
            target=next((p for p in nodes[edge.target_node_gid].inputs if p.get('key')==edge.target_port_key),None)
            if not source or not target: raise ValueError('port endpoint missing or wrong direction')
            if source.get('data_type')!=target.get('data_type') or source.get('unit')!=target.get('unit'): raise ValueError('port type or unit mismatch')


def clone_revision_graph(graph):
    """New persisted row identities; stable node keys retain business lineage."""
    import uuid
    from .models import GraphDraft
    data=graph.model_dump(mode='json')
    node_ids={n['gid']:str(uuid.uuid4()) for n in data['nodes']}
    item_ids={i['gid']:str(uuid.uuid4()) for i in data['items']}
    for n in data['nodes']:
        n['gid']=node_ids[n['gid']]
        for implementation in [n['implementation'],*n['implementation'].get('alternatives',[])]:
            implementation['source_item_gids']=[item_ids[g] for g in implementation['source_item_gids']]
    for e in data['edges']:
        e['gid']=str(uuid.uuid4());e['source_node_gid']=node_ids[e['source_node_gid']];e['target_node_gid']=node_ids[e['target_node_gid']]
    for i in data['items']:
        i['gid']=item_ids[i['gid']]
        if i['business_node_gid']:i['business_node_gid']=node_ids[i['business_node_gid']]
    for e in data['item_edges']:
        e['gid']=str(uuid.uuid4());e['source_item_gid']=item_ids[e['source_item_gid']];e['target_item_gid']=item_ids[e['target_item_gid']]
    for b in data['capability_bindings']+data['context_bindings']:
        b['gid']=str(uuid.uuid4());b['source_item_gid']=item_ids[b['source_item_gid']]
    if data['workspace']:
        for s in data['workspace']['scopes']:
            if s.get('business_node_gid'): s['business_node_gid']=node_ids[s['business_node_gid']]
        for v in data['workspace']['views']:
            for p in v['placements']:p['node_gid']=node_ids[p['node_gid']]
        for v in data['workspace']['variants']:
            if v['active_node_gids'] is not None:v['active_node_gids']=[node_ids[g] for g in v['active_node_gids']]
            v['node_overrides']={node_ids[g]:o for g,o in v['node_overrides'].items()}
            for o in v['node_overrides'].values():
                if o.get('implementation'):
                    for implementation in [o['implementation'],*o['implementation'].get('alternatives',[])]:
                        implementation['source_item_gids']=[item_ids[g] for g in implementation['source_item_gids']]
    return GraphDraft.model_validate(data)


def normalize_org_axes(graph):
    """Save-time canonical axes; reads remain compatible with old independent axes."""
    if not graph.workspace:return
    scopes={s.gid:s for s in graph.workspace.scopes}
    views={v.scope_gid:v for v in graph.workspace.views if v.view_type=='org'}
    planned=[]
    for gid,view in views.items():
        scope=scopes[gid];root=scope
        while root.parent_gid:root=scopes[root.parent_gid]
        root_view=views.get(root.gid)
        source=view if view.axis_mode in ('independent','overview') else (root_view or view)
        xs=list(source.axis.x_items)
        children=[s for s in graph.workspace.scopes if s.parent_gid==gid]
        ys=[s.title for s in children] if children else list(view.axis.y_items)
        if len(ys)!=len(set(ys)):raise ValueError('同级组织标题不可重复')
        effective_xs=['总览'] if view.axis_mode=='overview' else xs
        if any(p.x_item_key not in effective_xs or p.y_item_key not in ys for p in view.placements):
            raise ValueError('组织泳道需迁移：横轴继承顶级，纵轴使用下级组织标题')
        Axis.model_validate({**view.axis.model_dump(),"x_items":xs,"y_items":ys})
        planned.append((view,xs,ys,source.axis.column_width))
    for view,xs,ys,width in planned:view.axis.x_items=xs;view.axis.y_items=ys;view.axis.column_width=width
