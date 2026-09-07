"""Emit unpublished desktop-major evidence; never bypass the full Catalog gate."""
import json
from pathlib import Path
from backend.capability_v2.bootstrap import build_capability_registry
from backend.scripts.build_capability_catalog import current_release
ROOT=Path(__file__).resolve().parents[2]
def main():
    registry=build_capability_registry(ROOT)
    ids=json.loads((ROOT/'backend/tests/fixtures/desktop_contract_v1.json').read_text())
    try:current_release();errors=[]
    except ValueError as error:errors=str(error).split('; ')
    candidate={'status':'unpublished_candidate','published_catalog_unchanged':True,'machine_passed':False,'human_approved':False,'runtime_verified':False,'catalog_generation_errors':errors,'catalog_blocker_count':len(errors),'capabilities':[registry.get(i,2).descriptor.model_dump(mode='json') for i in ids], 'residual_schema_blockers':[
        {'capability':'craft.library.change.apply@2','fields':['record.spec','record.meta.<unknown>','meta.<unknown>'],'reason':'Authoritative request model declares untyped dict; nonempty arbitrary JSON requires a named business schema and remains rejected.'},
        {'capability':'craft.rule.library.change.apply@2','fields':['record.rule_definition'],'reason':'Untyped legacy rule JSON is not a closed rule definition contract; nonempty values remain rejected.'},
        {'capability':'project.task.change.apply.atomic.tasks_create@2','fields':['arguments.source_ref','arguments.progress_logs[]','arguments.attachments[]','arguments.feishu_groups[]','arguments.feishu_docs[]'],'reason':'Untyped dict/list item models have no authoritative named fields; nonempty records remain rejected.'},
        {'capability':'project.issue.change.apply.atomic.issues_create@2','fields':['arguments.source_ref','arguments.tracking_refs[]','arguments.attachments[]','arguments.feishu_groups[]','arguments.feishu_docs[]'],'reason':'Untyped dict/list item models have no authoritative named fields; nonempty records remain rejected.'}
    ]}
    (ROOT/'docs/governance/desktop-contract-v2-candidate.json').write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    pages=['# Desktop contract major 2 candidates','', 'These four Provider registrations are unpublished. The published Catalog and its 575 generated pages remain unchanged because the full release has 16 existing Knowledge collection blockers. No business approval or runtime success is asserted.','', 'Major 1 descriptors are frozen by `backend/tests/fixtures/desktop_contract_v1.json`. Tests verify the complete descriptors, major 2 request fields, wrong types, unknown fields, collection separation and result projections.','', 'The schemas add named legacy request-model fields only. Untyped nested JSON remains closed and is listed in the candidate artifact as unresolved business-schema debt.','']
    for d in candidate['capabilities']:pages.extend([f"## {d['id']}@2",'',f"Provider: `{d['owner_domain']}`. User confirmation retained; library v2 adds a closed operation-discriminated adapter over the existing business handler.",'','```json',json.dumps(d['input_schema'],ensure_ascii=False,indent=2),'```',''])
    (ROOT/'docs/governance/desktop-contract-v2-candidates.md').write_text('\n'.join(pages),encoding='utf-8')
    print(f"4 unpublished majors; {len(errors)} full Catalog blockers")
if __name__=='__main__':main()
