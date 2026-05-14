from fastapi import HTTPException
from jose import jwt as jose_jwt, JWTError
from app.config import settings


def get_user_id(token: str) -> str:
    try:
        payload = jose_jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated"
        )
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Токен недействителен")
