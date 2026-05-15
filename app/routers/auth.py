from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import bcrypt
from app.database import get_pg
from app.auth import create_access_token, create_refresh_token, verify_refresh_token, get_user_id
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""

class RefreshRequest(BaseModel):
    refresh_token: str

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode()[:72], hashed.encode())

@router.post("/register")
def register(body: RegisterRequest):
    pg = get_pg()
    cur = pg.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (body.email,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="Email уже занят")
    user_id = str(uuid.uuid4())
    password_hash = hash_password(body.password)
    cur.execute(
        "INSERT INTO users (id, email, password_hash, full_name) VALUES (%s, %s, %s, %s)",
        (user_id, body.email, password_hash, body.full_name)
    )
    cur.execute(
        "INSERT INTO subscriptions (user_id, credits_left) VALUES (%s, %s)",
        (user_id, 10)
    )
    return {"message": "Пользователь создан"}

@router.post("/login")
def login(body: LoginRequest):
    pg = get_pg()
    cur = pg.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (body.email,))
    user = cur.fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    return {
        "access_token": create_access_token(user["id"]),
        "refresh_token": create_refresh_token(user["id"]),
        "user": {"id": user["id"]},
    }

@router.post("/refresh")
def refresh(body: RefreshRequest):
    user_id = verify_refresh_token(body.refresh_token)
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
    }

@router.get("/me")
def me(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    pg = get_pg()
    cur = pg.cursor()
    cur.execute("SELECT id, email, full_name FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    cur.execute("SELECT credits_left FROM subscriptions WHERE user_id = %s", (user_id,))
    sub = cur.fetchone()
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "credits_left": sub["credits_left"] if sub else 0,
    }
