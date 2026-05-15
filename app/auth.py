from fastapi import HTTPException
import httpx
import jwt as pyjwt
from jwt import PyJWKClient

JWKS_URL = "https://jyalkrcrcxbcwiqehaae.supabase.co/auth/v1/.well-known/jwks"
_jwks_client = PyJWKClient(JWKS_URL)


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
        raise HTTPException(status_code=401, detail="Токен недействителен")
