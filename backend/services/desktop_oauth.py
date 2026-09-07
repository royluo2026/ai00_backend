"""Persistent desktop PKCE transactions and rotating opaque refresh families."""
from datetime import UTC, datetime
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode
from backend.db.connection import get_conn
from backend.services import jwt_service, user_service
from backend.services.feishu_service import feishu_service
from backend.capability_v2.identity import AuthenticatedPrincipal

CLIENT_ID = 'ai00.desktop.windows-x64'
REDIRECT_URI = 'ai00://auth/callback'

def digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()

def authenticate(code):
    info = feishu_service.exchange_code(code)
    if not info.get('open_id'):
        raise ValueError('invalid_grant')
    return user_service.get_or_create(**{key: info[key] for key in ('open_id', 'name', 'email', 'avatar_url', 'access_token', 'refresh_token', 'expires_in')})

def tenant(user):
    return str(user.get('team_id') or f"user:{user['gid']}")

class DesktopOAuth:
    def __init__(self, *, connect=get_conn, now=time.time, get_user=user_service.get_by_gid,
                 authenticate=authenticate, authorize_url=feishu_service.build_login_url):
        self.connect, self.now, self.get_user = connect, now, get_user
        self.authenticate, self.authorize_url = authenticate, authorize_url

    def start(self, binding):
        state = 'dt_' + secrets.token_urlsafe(32)
        # Provider callback uses its own random transaction ID, never caller state.
        url = self.authorize_url(state)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('INSERT INTO workmanship_base_desktop_transactions (transaction_hash,binding_json,expires_at) VALUES (%s,%s,%s)',
                        (digest(state), json.dumps(binding), int(self.now()) + 300))
        return {'authorization_url': url}

    def complete(self, provider_state, provider_code):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT * FROM workmanship_base_desktop_transactions WHERE transaction_hash=%s FOR UPDATE', (digest(provider_state),))
            row = cur.fetchone()
            if not row or row['consumed'] or row['code_hash'] or row['expires_at'] <= self.now():
                raise ValueError('invalid_grant')
            user = self.authenticate(provider_code)
            if not user or not user.get('is_active') or row['expires_at'] <= self.now():
                raise ValueError('invalid_grant')
            binding = json.loads(row['binding_json'])
            binding.update(user_id=str(user['gid']), tenant_id=tenant(user), authenticated_at=int(self.now()))
            code = secrets.token_urlsafe(32)
            cur.execute('UPDATE workmanship_base_desktop_transactions SET code_hash=%s,code_expires_at=%s,binding_json=%s WHERE transaction_hash=%s',
                        (digest(code), min(int(self.now()) + 60, row['expires_at']), json.dumps(binding), row['transaction_hash']))
        return REDIRECT_URI + '?' + urlencode({'code': code, 'state': binding['state']})

    def _user(self, binding):
        user = self.get_user(binding['user_id'])
        if not user or not user.get('is_active') or tenant(user) != binding['tenant_id']:
            raise ValueError('invalid_grant')
        return user

    def _session(self, binding, refresh, user):
        principal = AuthenticatedPrincipal(user_id=binding['user_id'], authentication_method='oauth2_pkce',
            authenticated_at=datetime.fromtimestamp(binding['authenticated_at'], UTC))
        access = jwt_service.sign_desktop_session(principal, tenant_id=binding['tenant_id'],
            installation_id=binding['installation_id'], consumer_version=binding['app_version'])
        # Expiry follows the signed JWT, not a separate client-side assumption.
        expires = int(jwt_service.verify(access)['exp'] - time.time())
        return {'access_token': access, 'refresh_token': refresh, 'expires_in': expires,
                'user': {key: str(user[key]) for key in ('gid', 'name', 'email', 'avatar_url', 'org_role') if user.get(key) is not None}}

    @staticmethod
    def _matches(binding, request):
        return all(binding[key] == request[key] for key in ('client_id', 'installation_id', 'app_version'))

    def exchange(self, request):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT * FROM workmanship_base_desktop_transactions WHERE code_hash=%s FOR UPDATE', (digest(request['code']),))
            row = cur.fetchone()
            if not row or row['consumed'] or row['code_expires_at'] <= self.now():
                raise ValueError('invalid_grant')
            binding = json.loads(row['binding_json'])
            challenge = base64.urlsafe_b64encode(hashlib.sha256(request['code_verifier'].encode('ascii')).digest()).rstrip(b'=').decode()
            if not self._matches(binding, request) or binding['redirect_uri'] != request['redirect_uri'] or not hmac.compare_digest(binding['code_challenge'], challenge):
                raise ValueError('invalid_grant')
            user = self._user(binding)
            refresh, family = secrets.token_urlsafe(48), secrets.token_hex(32)
            result = self._session(binding, refresh, user)
            cur.execute('UPDATE workmanship_base_desktop_transactions SET consumed=1 WHERE transaction_hash=%s', (row['transaction_hash'],))
            # Refresh families contain no authorization code, verifier or caller state.
            bound = {key: binding[key] for key in ('client_id', 'installation_id', 'app_version', 'user_id', 'tenant_id', 'authenticated_at')}
            cur.execute('INSERT INTO workmanship_base_desktop_families (family_id,binding_json,current_hash,expires_at) VALUES (%s,%s,%s,%s)',
                        (family, json.dumps(bound), digest(refresh), int(self.now()) + 30 * 86400))
            cur.execute('INSERT INTO workmanship_base_desktop_refresh_tokens (token_hash,family_id) VALUES (%s,%s)', (digest(refresh), family))
        return result

    def refresh(self, request, *, revoke=False):
        token_hash = digest(request['refresh_token'])
        result = None
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT family_id FROM workmanship_base_desktop_refresh_tokens WHERE token_hash=%s', (token_hash,))
            token = cur.fetchone()
            if not token:
                raise ValueError('invalid_grant')
            # Lock family first for every old/new token, so concurrent reuse fences
            # the token issued by the winning request before another rotation.
            cur.execute('SELECT * FROM workmanship_base_desktop_families WHERE family_id=%s FOR UPDATE', (token['family_id'],))
            family = cur.fetchone()
            if not family:
                raise ValueError('invalid_grant')
            binding = json.loads(family['binding_json'])
            invalid = family['revoked'] or family['expires_at'] <= self.now() or not hmac.compare_digest(family['current_hash'], token_hash) or not self._matches(binding, request)
            try: user = self._user(binding)
            except ValueError: invalid = True
            if invalid or revoke:
                # Commit revocation before raising: raising inside get_conn would
                # roll back and permit the stolen/new token family to survive.
                cur.execute('UPDATE workmanship_base_desktop_families SET revoked=1 WHERE family_id=%s', (family['family_id'],))
                if revoke and not invalid: result = {'ok': True}
            else:
                refresh = secrets.token_urlsafe(48)
                result = self._session(binding, refresh, user)
                cur.execute('UPDATE workmanship_base_desktop_families SET current_hash=%s WHERE family_id=%s', (digest(refresh), family['family_id']))
                cur.execute('INSERT INTO workmanship_base_desktop_refresh_tokens (token_hash,family_id) VALUES (%s,%s)', (digest(refresh), family['family_id']))
        if result is None:
            raise ValueError('invalid_grant')
        return result
