"""Upgrade-only attachment migration from authoritative owner records, bounded/resumable.

Apply the Base legacy_artifact_bindings DDL first. This command never accepts
object keys, caller paths or attachment manifests; each owner rechecks its rows.
"""
import argparse
import json
from types import SimpleNamespace
from backend.platform_sdk.historical_artifacts import reference_hash


def migrate(owner,kind,context,*,after='',limit=100,apply=False):
    if not 1<=limit<=500:raise ValueError('limit must be 1..500')
    if owner=='project':
        from plugins.project_management.project_management_backend.capabilities import desktop_attachments as service
        if kind not in ('task','issue'):raise ValueError('invalid parent type')
    elif owner=='knowledge':
        from plugins.knowledge.knowledge_backend.capabilities import desktop_attachments as service
        if kind not in ('entry','item'):raise ValueError('invalid parent type')
    elif owner=='craft':
        if kind=='bop_version':
            from plugins.craft.craft_backend.capabilities import desktop_pictures as service
        elif kind=='rule':
            from plugins.craft.craft_backend.capabilities import desktop_attachments as service
        else:raise ValueError('invalid parent type')
    else:raise ValueError('invalid owner')
    parents=service.migration_parents(kind,context.user_gid,after,limit)
    migrated=0;discovered=0;rejected=[]
    for parent in parents:
        gid=parent['gid']
        try:
            _,values=service.parent_attachments(kind,gid,context)
            for value in values:
                if value.get('artifact_ref') or str(value.get('url') or '').startswith('artifact:'):continue
                discovered+=1
                if apply:
                    if kind=='bop_version':service.resolve_picture({'version_gid':gid,'reference_hash':reference_hash(value)},context)
                    else:service.resolve_attachment({'parent_type':kind,'parent_gid':gid,'reference_hash':reference_hash(value)},context)
                    migrated+=1
        except (ValueError,OSError,RuntimeError) as exc:
            rejected.append({'parent_gid':gid,'error':getattr(exc,'code',type(exc).__name__)})
    return {'owner':owner,'parent_type':kind,'parents':len(parents),'discovered':discovered,'migrated':migrated,'rejected':rejected,'next_after':parents[-1]['gid'] if parents else after,'has_more':len(parents)==limit,'applied':apply}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner',required=True,choices=('project','knowledge','craft'));parser.add_argument('--parent-type',required=True)
    parser.add_argument('--actor-gid',required=True);parser.add_argument('--tenant-gid',required=True)
    parser.add_argument('--after',default='');parser.add_argument('--limit',type=int,default=100);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();context=SimpleNamespace(user_gid=args.actor_gid,team_gid=args.tenant_gid,active_roles=())
    result=migrate(args.owner,args.parent_type,context,after=args.after,limit=args.limit,apply=args.apply)
    print(json.dumps(result,ensure_ascii=False));return int(bool(result['rejected']))


if __name__=='__main__':raise SystemExit(main())
