"""Public Base Feishu client surface for official domains."""
from backend.services.feishu_service import feishu_service


def user_credential(context):
    """Resolve a user's delegated credential inside the trusted owner boundary."""
    from backend.services.user_service import get_feishu_token
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    token=get_feishu_token(context.user_gid)
    if not token: raise CapabilityBusinessError('authentication_required','Feishu authorization is required.')
    return token

__all__ = ["feishu_service","user_credential"]
