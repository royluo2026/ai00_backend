from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import jwt,pytest
from backend.capability_v2.identity import AuthenticatedPrincipal,IdentityError
from backend.services import jwt_service,user_service

@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv('TABLE_PREFIX','test_')
    monkeypatch.setenv('AI00_DEMO_ACCOUNT_GID','7001')
    monkeypatch.setenv('AI00_DEMO_PROJECT_GID','8001')
    monkeypatch.delenv('AI00_DEPLOY_PROFILE',raising=False)
    monkeypatch.setattr(user_service,'get_by_gid',lambda gid:{'gid':gid,'is_active':True,'system_role':'member','org_role':'member','team_id':None})
    monkeypatch.setattr(jwt_service,'get_settings',lambda:SimpleNamespace(jwt_secret='unit-test-secret-must-be-at-least-32-bytes'))

def principal(method='demo_password',user='7001'):
    return AuthenticatedPrincipal(user_id=user,authentication_method=method,authenticated_at=datetime.now(timezone.utc))

def issue(p):
    return jwt_service.sign_demo_desktop_session(p,installation_id='demo-install-1',consumer_version='1.0.0')

def test_verified_demo_member_gets_bound_desktop_claim(demo):
    claims=jwt.decode(issue(principal()),'unit-test-secret-must-be-at-least-32-bytes',algorithms=['HS256'])
    assert claims['sub']=='7001'
    assert claims['desktop_consumer']['tenant_id']=='user:7001'
    assert claims['authentication_method']=='demo_password'
    assert claims['system_role']=='member'

@pytest.mark.parametrize('method',['jwt','oauth2_pkce','caller_supplied'])
def test_demo_issuer_does_not_misrepresent_authentication(demo,method):
    with pytest.raises(IdentityError):issue(principal(method))

def test_demo_issuer_rejects_foreign_actor_and_production(demo,monkeypatch):
    with pytest.raises(IdentityError):issue(principal(user='7002'))
    monkeypatch.setenv('AI00_DEPLOY_PROFILE','production')
    with pytest.raises(IdentityError):issue(principal())

def test_demo_issuer_reads_persisted_active_member(demo,monkeypatch):
    monkeypatch.setattr(user_service,'get_by_gid',lambda gid:{'gid':gid,'is_active':False,'system_role':'super_admin','org_role':'super_admin'})
    with pytest.raises(IdentityError):issue(principal())

@pytest.mark.parametrize('delta',[timedelta(minutes=1),-timedelta(hours=2)])
def test_demo_issuer_rejects_future_or_expired_authentication(demo,delta):
    p=principal().model_copy(update={'authenticated_at':datetime.now(timezone.utc)+delta})
    with pytest.raises(IdentityError):issue(p)

def test_demo_issuer_rejects_service_actor(demo):
    p=AuthenticatedPrincipal(service_id='demo-service',authentication_method='demo_password',authenticated_at=datetime.now(timezone.utc))
    with pytest.raises(IdentityError):issue(p)
