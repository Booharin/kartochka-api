from fastapi import HTTPException
import jwt as pyjwt
from jwt import PyJWKClient
from app.config import settings

JWKS_URL = "https://jyalkrcrcxbcwiqehaae.supabase.co/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(
    JWKS_URL,
    headers={"apikey": settings.supabase_anon_key},
    lifespan=3600,
    cache_keys=True,
)


def get_user_id(token: str) -> str:
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        return payload["sub"]
    except Exception as e:
        print(f"[auth] JWT error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail="Токен недействителен")
