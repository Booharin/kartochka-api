from fastapi import HTTPException
from jose import jwt as jose_jwt, JWTError
import httpx, json

JWKS_URL = "https://jyalkrcrcxbcwiqehaae.supabase.co/auth/v1/.well-known/jwks"
_jwks: dict | None = None


def _load_jwks() -> dict:
    global _jwks
    if _jwks is None:
        resp = httpx.get(JWKS_URL, timeout=10)
        _jwks = resp.json()
    return _jwks


def get_user_id(token: str) -> str:
    try:
        jwks = _load_jwks()
        payload = jose_jwt.decode(
            token,
            jwks,
            algorithms=["ES256"],
            audience="authenticated",
        )
        return payload["sub"]
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Токен недействителен")
