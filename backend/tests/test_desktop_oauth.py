"""Desktop OAuth state, PKCE and refresh replay regression tests.

SQLite executes production SQL with BEGIN IMMEDIATE replacing row locks; native
MySQL/OceanBase deployment remains a separate integration requirement.
"""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs
import hashlib
import base64
import json
import sqlite3
import threading
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
assert (ROOT / 'backend/services/desktop_oauth.py').exists(), 'desktop PKCE service is missing'
from backend.services.desktop_oauth import DesktopOAuth, CLIENT_ID, REDIRECT_URI
from backend.routers import desktop_auth
from backend.services import jwt_service

class Cursor:
    def __init__(self, conn): self.cursor = conn.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.cursor.close()
    def execute(self, sql, params=()): return self.cursor.execute(sql.replace('%s', '?').replace(' FOR UPDATE', ''), params)
    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None
class Connection:
    def __init__(self, conn): self.conn = conn
    def cursor(self): return Cursor(self.conn)

@pytest.fixture
def runtime(tmp_path, monkeypatch):
    database = tmp_path / 'oauth.db'
    sql = (ROOT / 'backend/db/migrations/202609070002_base_desktop_oauth.sql').read_text()
    conn = sqlite3.connect(database)
    conn.executescript(sql.replace(' ENGINE=InnoDB', ''))
    conn.close()
    @contextmanager
    def connect():
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN IMMEDIATE')
        try:
            yield Connection(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally: conn.close()
    clock = [1000000]
    user = {'gid': 'user-1', 'team_id': 'tenant-1', 'is_active': True, 'name': 'User'}
    monkeypatch.setattr(jwt_service, 'get_settings', lambda: SimpleNamespace(jwt_secret='test-desktop-secret-32-bytes-long', jwt_expire_hours=1))
    service = DesktopOAuth(connect=connect, now=lambda: clock[0], get_user=lambda gid: dict(user),
        authenticate=lambda code: dict(user), authorize_url=lambda state: 'https://open.feishu.cn/open-apis/authen/v1/authorize?state=' + state)
    monkeypatch.setattr(desktop_auth, 'service', service)
    app = FastAPI(); app.include_router(desktop_auth.router)
    return service, TestClient(app), clock, user, database

VERIFIER = 'a' * 43
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b'=').decode()
def start_body(**changes):
    return dict(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, installation_id='installation-1', app_version='1.0.3', state='s' * 43, code_challenge=CHALLENGE, code_challenge_method='S256', **changes)
def begin(runtime):
    service, client, *_ = runtime
    response = client.post('/auth/desktop/start', json=start_body())
    assert response.status_code == 200, response.text
    provider_state = parse_qs(urlparse(response.json()['authorization_url']).query)['state'][0]
    callback = service.complete(provider_state, 'verified-provider-code')
    assert callback.startswith('ai00://auth/callback?')
    query = parse_qs(urlparse(callback).query)
    assert set(query) == {'code', 'state'} and query['state'] == ['s' * 43]
    return query['code'][0]
def exchange(client, code, **changes):
    body = dict(grant_type='authorization_code', client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, installation_id='installation-1', app_version='1.0.3', code=code, code_verifier=VERIFIER)
    body.update(changes)
    return client.post('/auth/desktop/token', json=body)
def rotate(client, token, **changes):
    body = dict(grant_type='refresh_token', client_id=CLIENT_ID, installation_id='installation-1', app_version='1.0.3', refresh_token=token)
    body.update(changes)
    return client.post('/auth/desktop/token', json=body)

def test_pkce_exchange_and_bound_signed_claim(runtime):
    code = begin(runtime); response = exchange(runtime[1], code)
    assert response.status_code == 200, response.text
    session = response.json()
    assert 1 <= session['expires_in'] <= 900
    claims = jwt_service.verify(session['access_token'])
    assert claims['desktop_consumer'] == dict(consumer_id='ai00.desktop.windows-x64', tenant_id='tenant-1', installation_id='installation-1', consumer_version='1.0.3')
    assert exchange(runtime[1], code).status_code == 401
    assert session['refresh_token'].encode() not in runtime[4].read_bytes()
    assert session['access_token'].encode() not in runtime[4].read_bytes()

@pytest.mark.parametrize('changes', [{'code_verifier':'b'*43}, {'installation_id':'other'}, {'app_version':'9.0.0'}, {'redirect_uri':'https://evil.example'}, {'client_id':'evil'}, {'tenant_id':'evil'}, {'consumer_id':'ai00.web'}])
def test_wrong_exchange_binding_rejected(runtime, changes):
    code = begin(runtime)
    assert exchange(runtime[1], code, **changes).status_code in (400, 401)

def test_duplicate_unknown_and_secret_errors(runtime):
    client = runtime[1]
    for body in [json.dumps(start_body())[:-1]+',"state":"secret"}', json.dumps({**start_body(), 'tenant_id':'secret'})]:
        response = client.post('/auth/desktop/start', content=body, headers={'Content-Type':'application/json'})
        assert response.status_code == 400
        assert 'secret' not in response.text

def test_expiry_and_provider_replay(runtime):
    service, client, clock, *_ = runtime
    started = client.post('/auth/desktop/start', json=start_body()).json()
    state = parse_qs(urlparse(started['authorization_url']).query)['state'][0]
    service.complete(state, 'provider-code')
    with pytest.raises(ValueError): service.complete(state, 'provider-code')
    code = begin(runtime); clock[0] += 61
    assert exchange(client, code).status_code == 401

def test_refresh_rotation_reuse_revokes_new_token(runtime):
    client = runtime[1]
    first = exchange(client, begin(runtime)).json()
    second = rotate(client, first['refresh_token'])
    assert second.status_code == 200
    assert rotate(client, first['refresh_token']).status_code == 401
    assert rotate(client, second.json()['refresh_token']).status_code == 401

def test_concurrent_code_has_one_winner(runtime):
    code = begin(runtime)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: exchange(runtime[1], code).status_code, range(2)))
    assert sorted(results) == [200, 401]

def test_concurrent_refresh_reuse_revokes_family(runtime):
    token = exchange(runtime[1], begin(runtime)).json()['refresh_token']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: rotate(runtime[1], token), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 401]
    winner = next(r for r in responses if r.status_code == 200)
    assert rotate(runtime[1], winner.json()['refresh_token']).status_code == 401

def test_tenant_change_and_revoke(runtime):
    client = runtime[1]
    token = exchange(client, begin(runtime)).json()['refresh_token']
    runtime[3]['team_id'] = 'tenant-2'
    assert rotate(client, token).status_code == 401
    runtime[3]['team_id'] = 'tenant-1'
    token = exchange(client, begin(runtime)).json()['refresh_token']
    response = client.post('/auth/desktop/revoke', json=dict(client_id=CLIENT_ID, refresh_token=token, installation_id='installation-1', app_version='1.0.3'))
    assert response.status_code == 200
    assert rotate(client, token).status_code == 401

def test_real_auth_router_provider_callback_and_duplicate_rejection(runtime, monkeypatch):
    from backend.routers import auth
    app = FastAPI(); app.include_router(auth.router); app.include_router(desktop_auth.router)
    client = TestClient(app)
    response = client.post('/auth/desktop/start', json=start_body())
    assert response.status_code == 200
    state = parse_qs(urlparse(response.json()['authorization_url']).query)['state'][0]
    bad = client.get('/auth/feishu/callback', params=[('state', state), ('state', state), ('code', 'provider-code')], follow_redirects=False)
    assert bad.status_code == 400
    response = client.get('/auth/feishu/callback', params={'state':state, 'code':'provider-code'}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['location'].startswith('ai00://auth/callback?code=')
    assert 'token' not in response.headers['location']
    assert client.get('/auth/feishu/callback', params={'state':state, 'code':'provider-code'}, follow_redirects=False).status_code == 400


def test_canonical_bearer_and_legacy_token_conflict(runtime, monkeypatch):
    from fastapi import Depends
    from backend.routers import deps
    monkeypatch.setattr(deps.user_service, 'get_by_gid', lambda _: dict(runtime[3]))
    app = FastAPI()
    @app.get('/identity')
    def identity(principal=Depends(deps.get_authenticated_principal), user=Depends(deps.get_current_user)):
        return {'consumer':principal.desktop_consumer.consumer_id, 'user':user['gid']}
    token = exchange(runtime[1], begin(runtime)).json()['access_token']
    client = TestClient(app)
    assert client.get('/identity', headers={'Authorization':'Bearer ' + token}).status_code == 200
    assert client.get('/identity', headers={'X-AI00-Token':token}).status_code == 200
    assert client.get('/identity', headers={'Authorization':'Bearer ' + token, 'X-AI00-Token':'other'}).status_code == 401
    assert client.get('/identity', headers=[('Authorization','Bearer '+token),('Authorization','Bearer '+token)]).status_code == 401

def test_provider_response_cannot_outlive_transaction(runtime):
    service, client, clock, *_ = runtime
    result = client.post('/auth/desktop/start', json=start_body()).json()
    state = parse_qs(urlparse(result['authorization_url']).query)['state'][0]
    def delayed(code):
        clock[0] += 301
        return dict(runtime[3])
    service.authenticate = delayed
    with pytest.raises(ValueError): service.complete(state, 'provider-code')


def test_refresh_expiry_and_bound_identity(runtime):
    client, clock = runtime[1], runtime[2]
    token = exchange(client, begin(runtime)).json()['refresh_token']
    assert rotate(client, token, installation_id='another-installation').status_code == 401
    assert rotate(client, token).status_code == 401
    token = exchange(client, begin(runtime)).json()['refresh_token']
    clock[0] += 30 * 86400 + 1
    assert rotate(client, token).status_code == 401
