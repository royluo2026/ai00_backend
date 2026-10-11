import json
import pytest
from plugins.simulation.simulation_backend.application.demo_environment_labels import anonymous_runtime_model
from plugins.simulation.simulation_backend.domain.plmxml_environment_codec import (
    EnvironmentRuntimeModel,EnvironmentModelDocument,AlternateHierarchyProjection,EnvironmentPlacementProjection)

def model():
    document=EnvironmentModelDocument('doc1','primary','L5-12345.jt','model/vnd.jt',{'sha256':'a'*64},'b'*64,'a'*64,'cloud')
    placement=EnvironmentPlacementProjection('projection1','stable1','L5 零件 12345',None,(),True)
    hierarchy=AlternateHierarchyProjection('L5 总成','hierarchy1',('projection1',),placements=(placement,))
    return EnvironmentRuntimeModel('env1',(document,),(hierarchy,))

def test_demo_labels_are_anonymous_without_changing_model_identity(monkeypatch,tmp_path):
    monkeypatch.setenv('TABLE_PREFIX','test_');monkeypatch.setenv('AI00_DEMO_ACCOUNT_GID','7001');monkeypatch.setenv('AI00_DEMO_PROJECT_GID','8001')
    monkeypatch.delenv('AI00_DEPLOY_PROFILE',raising=False)
    aliases=tmp_path/'aliases.json';aliases.write_text(json.dumps({'schema':'ai00.demo.display-aliases.v1','aliases':{'L5':'演示项目 A','12345':'PART-000001'}}),encoding='utf-8')
    monkeypatch.setenv('AI00_DEMO_DISPLAY_ALIASES_FILE',str(aliases))
    original=model();copy=anonymous_runtime_model(original,'7001')
    assert copy.documents[0].display_name=='演示项目 A-PART-000001.jt'
    assert copy.hierarchies[0].placements[0].name=='演示项目 A 零件 PART-000001'
    assert copy.documents[0].artifact_ref==original.documents[0].artifact_ref
    assert copy.documents[0].content_sha256==original.documents[0].content_sha256
    assert copy.hierarchies[0].placements[0].stable_identity=='stable1'
    assert copy.hierarchies[0].root_refs==original.hierarchies[0].root_refs
    assert original.documents[0].display_name=='L5-12345.jt'
    from plugins.simulation.simulation_backend.application.environment_materialization import build_runtime_package
    package=build_runtime_package({'runtime_model':copy,'version_gid':'v1'})
    assert b'L5' not in package.top_level_content
    assert b'12345' not in package.top_level_content
    assert 'L5' not in package.dependencies[0].package_path
    assert '12345' not in package.dependencies[0].package_path
    assert package.dependencies[0].content_sha256=='sha256:'+'a'*64

def test_ordinary_users_have_no_demo_overlay(monkeypatch):
    monkeypatch.setenv('TABLE_PREFIX','test_');monkeypatch.setenv('AI00_DEMO_ACCOUNT_GID','7001');monkeypatch.setenv('AI00_DEMO_PROJECT_GID','8001')
    original=model();assert anonymous_runtime_model(original,'7002')==original
