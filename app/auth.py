from fastapi import HTTPException
from datetime import datetime, timedelta
import jwt as pyjwt
from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return pyjwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )

def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return pyjwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )

def get_user_id(token: str) -> str:
    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Неверный тип токена")
        return payload["sub"]
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истёк")
    except Exception:
        raise HTTPException(status_code=401, detail="Токен недействителен")

def verify_refresh_token(token: str) -> str:
    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Неверный тип токена")
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Refresh токен недействителен")
