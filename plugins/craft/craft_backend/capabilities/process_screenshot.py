"""Idempotently associate a verified screenshot ArtifactRef with a Craft operation."""
from __future__ import annotations

import json
import uuid

from backend.capability_v2.contracts import ArtifactRef
from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
    EvidenceRef,
)
from backend.platform_sdk.artifacts import require_artifact

from ..data.connection import get_craft_conn
from ..services.bop_picture_refs import screenshot_picture
from .provider import register_capability


class ProcessScreenshotRepository:
    def attach(self, *, bop_version_gid, operation_id, capture_run_id, artifact_ref, actor_gid):
        return self.attach_many(bop_version_gid=bop_version_gid, capture_run_id=capture_run_id,
            items=[{'operation_id':operation_id,'artifact_ref':artifact_ref}],actor_gid=actor_gid)[0]

    def attach_many(self, *, bop_version_gid, capture_run_id, items, actor_gid, expected_revision=None):
        rows=[]
        with get_craft_conn() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SELECT gid, revision FROM workmanship_bop_bop_versions WHERE gid=%s AND is_deleted=0 FOR UPDATE',(bop_version_gid,))
                    version=cursor.fetchone()
                    if not version:raise CapabilityBusinessError('bop_version_not_found','BOP version not found')
                    if expected_revision is not None and version.get('revision')!=expected_revision:
                        raise CapabilityBusinessError('bop_revision_conflict','BOP changed since capture preparation')
                    for item in items:
                        rows.append(self._attach_one(cursor,bop_version_gid=bop_version_gid,capture_run_id=capture_run_id,actor_gid=actor_gid,**item))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return rows

    def _attach_one(self,cursor,*,bop_version_gid,operation_id,capture_run_id,artifact_ref,actor_gid):
        cursor.execute("SELECT gid, process_flow_pic FROM workmanship_bop_bop_entries WHERE gid=%s AND version_gid=%s AND is_deleted=0 AND node_type IN ('process','bop_process','operation','bop_operation','bop_steps','step')",(operation_id,bop_version_gid))
        entry=cursor.fetchone()
        if not entry:raise CapabilityBusinessError('bop_entry_not_found','BOP operation not found')
        cursor.execute('SELECT gid, artifact_ref_json, artifact_sha256 FROM workmanship_craft_process_screenshots WHERE bop_version_gid=%s AND operation_id=%s AND capture_run_id=%s',(bop_version_gid,operation_id,capture_run_id))
        current=cursor.fetchone()
        if current:
            encoded=current['artifact_ref_json']; old=json.loads(encoded) if isinstance(encoded,str) else encoded
            if old!=artifact_ref:raise CapabilityBusinessError('idempotency_conflict','Capture key is bound to another artifact')
            return self._result(current['gid'],bop_version_gid,operation_id,capture_run_id,encoded)
        gid='craft-shot-'+uuid.uuid4().hex
        cursor.execute('INSERT INTO workmanship_craft_process_screenshots (gid,bop_version_gid,operation_id,capture_run_id,artifact_ref_json,artifact_sha256,created_by_gid) VALUES (%s,%s,%s,%s,%s,%s,%s)',(gid,bop_version_gid,operation_id,capture_run_id,json.dumps(artifact_ref,ensure_ascii=False,separators=(',',':')),artifact_ref['sha256'],actor_gid))
        from ..services.bop_picture_refs import normalize_bop_pictures
        pictures=normalize_bop_pictures(entry.get('process_flow_pic'))
        pictures.append({**screenshot_picture(artifact_ref),'screenshot_gid':gid,'capture_run_id':capture_run_id,'artifact_ref':artifact_ref})
        projection=json.dumps(pictures,ensure_ascii=False,separators=(',',':'))
        cursor.execute('UPDATE workmanship_bop_bop_entries SET process_flow_pic=%s WHERE gid=%s AND version_gid=%s',(projection,operation_id,bop_version_gid))
        return self._result(gid,bop_version_gid,operation_id,capture_run_id,artifact_ref)

    @staticmethod
    def _result(gid, bop_version_gid, operation_id, capture_run_id, artifact_ref_json):
        artifact_ref = artifact_ref_json
        if isinstance(artifact_ref, str):
            artifact_ref = json.loads(artifact_ref)
        return {
            "screenshot_gid": gid,
            "bop_version_gid": bop_version_gid,
            "operation_id": operation_id,
            "capture_run_id": capture_run_id,
            "artifact_ref": artifact_ref,
        }


class ProcessScreenshotProvider:
    def __init__(self, repository=None, artifact_resolver=require_artifact):
        self.repository = repository or ProcessScreenshotRepository()
        self.artifact_resolver = artifact_resolver

    def _verified_artifact(self, payload: dict, context: CapabilityContext) -> dict:
        try:
            supplied = ArtifactRef.model_validate(payload["artifact_ref"])
        except (KeyError, ValueError) as exc:
            raise CapabilityBusinessError(
                "screenshot_artifact_invalid", "Screenshot ArtifactRef is invalid"
            ) from exc
        if not supplied.media_type.startswith("image/"):
            raise CapabilityBusinessError(
                "screenshot_artifact_invalid", "Screenshot artifact must be an image"
            )
        try:
            verified = self.artifact_resolver(
                supplied.model_dump(mode="json"), context,
                resource_refs=(f"craft-bop-version:{payload['bop_version_gid']}",),
            )
        except Exception as exc:
            raise CapabilityBusinessError(
                "screenshot_artifact_invalid", "Artifact Service did not verify the screenshot"
            ) from exc
        try:
            confirmed = ArtifactRef.model_validate(verified)
        except ValueError as exc:
            raise CapabilityBusinessError(
                "screenshot_artifact_invalid", "Artifact Service returned an invalid reference"
            ) from exc
        if confirmed != supplied:
            raise CapabilityBusinessError(
                "screenshot_artifact_invalid", "Artifact Service did not confirm the exact reference"
            )
        verified = confirmed.model_dump(mode="json")
        return verified

    def attach_batch(self, payload, context):
        items=payload.get('items')
        if not isinstance(items,list) or not 1<=len(items)<=2000 or len({item.get('operation_id') for item in items})!=len(items):
            raise CapabilityBusinessError('screenshot_artifact_invalid','Batch operations must be bounded and unique')
        verified=[{'operation_id':item['operation_id'],'artifact_ref':self._verified_artifact({'bop_version_gid':payload['bop_version_gid'],**item},context)} for item in items]
        rows=self.repository.attach_many(bop_version_gid=payload['bop_version_gid'],capture_run_id=payload['capture_run_id'],expected_revision=payload['expected_revision'],items=verified,actor_gid=context.user_gid)
        return CapabilityOutput(data={'items':rows},evidence=tuple(EvidenceRef(kind='craft.process_screenshot',reference=f"craft-screenshot:{row['screenshot_gid']}",digest='sha256:'+row['artifact_ref']['sha256']) for row in rows))

    def attach(self, payload: dict, context: CapabilityContext) -> CapabilityOutput:
        verified=self._verified_artifact(payload,context)
        row = self.repository.attach(
            bop_version_gid=payload["bop_version_gid"],
            operation_id=payload["operation_id"],
            capture_run_id=payload["capture_run_id"],
            artifact_ref=verified,
            actor_gid=context.user_gid,
        )
        return CapabilityOutput(
            data=row,
            evidence=(EvidenceRef(
                kind="craft.process_screenshot",
                reference=f"craft-screenshot:{row['screenshot_gid']}",
                digest="sha256:" + verified["sha256"],
            ),),
        )


def register_process_screenshot_capability(registry, repository=None, artifact_resolver=require_artifact):
    provider = ProcessScreenshotProvider(repository, artifact_resolver)
    register_capability(registry, CapabilitySpec(
        id='craft.process_screenshot.attach',version=2,owner='craft',
        description='Atomically attach a bounded batch of exact finalized screenshots to one revision-pinned BOP while preserving existing pictures.',
        risk=CapabilityRisk.WRITE,confirmation='user',idempotent=True,permissions=('craft.write',),
        tags=('craft','bop','screenshot','experimental'),plugin_callable=True,
    ),provider.attach_batch)
    register_capability(registry, CapabilitySpec(
        id="craft.process_screenshot.attach", version=1, owner="craft",
        description="Associate one verified screenshot artifact with one BOP process or operation.",
        use_when="A governed capture run has finalized a screenshot for a BOP process or operation.",
        do_not_use_when="The image has not been finalized by the Artifact Service.",
        risk=CapabilityRisk.WRITE, confirmation="user", idempotent=True,
        permissions=("craft.write",),
        input_schema={}, output_schema={},
        tags=("craft", "bop", "screenshot"), plugin_callable=True,
    ), provider.attach)


__all__ = [
    "ProcessScreenshotProvider", "ProcessScreenshotRepository",
    "register_process_screenshot_capability",
]
