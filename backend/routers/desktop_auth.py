"""Closed desktop OAuth HTTP adapter; no caller-selected user/tenant/consumer."""
import json
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from backend.services.desktop_oauth import DesktopOAuth, CLIENT_ID, REDIRECT_URI

router = APIRouter(prefix='/auth/desktop', tags=['auth'])
service = DesktopOAuth()
class Binding(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    client_id: Literal['ai00.desktop.windows-x64']
    installation_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
    app_version: str = Field(pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$', max_length=128)
class Start(Binding):
    redirect_uri: Literal['ai00://auth/callback']
    state: str = Field(pattern=r'^[A-Za-z0-9_-]{43,128}$')
    code_challenge: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    code_challenge_method: Literal['S256']
class Exchange(Binding):
    grant_type: Literal['authorization_code']
    redirect_uri: Literal['ai00://auth/callback']
    code: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    code_verifier: str = Field(pattern=r'^[A-Za-z0-9._~-]{43,128}$')
class Refresh(Binding):
    grant_type: Literal['refresh_token']
    refresh_token: str = Field(pattern=r'^[A-Za-z0-9_-]{64}$')
class Revoke(Binding):
    refresh_token: str = Field(pattern=r'^[A-Za-z0-9_-]{64}$')

def pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError('duplicate_field')
        result[key] = value
    return result
async def body(request):
    if request.query_params or request.headers.get('content-type', '').split(';')[0] != 'application/json':
        raise HTTPException(400, detail={'code':'invalid_request'})
    data = bytearray()
    try:
        async for part in request.stream():
            data.extend(part)
            if len(data) > 16384: raise ValueError('request_too_large')
        return json.loads(data, object_pairs_hook=pairs)
    except (ValueError, UnicodeError):
        raise HTTPException(400, detail={'code':'invalid_request'}) from None

def invoke(model, payload, fn):
    try: validated = model.model_validate(payload).model_dump()
    except ValidationError: raise HTTPException(400, detail={'code':'invalid_request'}) from None
    try: result = fn(validated)
    except ValueError: raise HTTPException(401, detail={'code':'invalid_grant'}) from None
    except Exception: raise HTTPException(503, detail={'code':'desktop_auth_unavailable'}) from None
    return JSONResponse(result, headers={'Cache-Control':'no-store', 'Pragma':'no-cache'})

@router.post('/start')
async def start(request: Request):
    return invoke(Start, await body(request), service.start)
@router.post('/token')
async def token(request: Request):
    data = await body(request)
    if not isinstance(data, dict): raise HTTPException(400, detail={'code':'invalid_request'})
    model, fn = (Exchange, service.exchange) if data.get('grant_type') == 'authorization_code' else (Refresh, service.refresh)
    return invoke(model, data, fn)
@router.post('/revoke')
async def revoke(request: Request):
    return invoke(Revoke, await body(request), lambda payload: service.refresh(payload, revoke=True))
