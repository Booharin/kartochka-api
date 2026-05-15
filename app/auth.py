from fastapi import HTTPException
import httpx
from jose import jwt as jose_jwt, JWTError

JWKS_URL = "https://jyalkrcrcxbcwiqehaae.supabase.co/auth/v1/.well-known/jwks"
_jwks_cache = None


async def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(JWKS_URL)
            _jwks_cache = resp.json()
    return _jwks_cache


def get_user_id(token: str) -> str:
    from app.database import get_supabase
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        return response.user.id
    except:
        raise HTTPException(status_code=401, detail="Токен недействителен")
