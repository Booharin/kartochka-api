from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from app.database import get_supabase, get_supabase_admin

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Модели запросов ---

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str


# --- Регистрация ---

@router.post("/register")
async def register(body: RegisterRequest):
    supabase = get_supabase()
    try:
        response = supabase.auth.sign_up({
            "email": body.email,
            "password": body.password,
            "options": {
                "data": {"full_name": body.full_name}
            }
        })
        return {"message": "Проверьте email для подтверждения", "user_id": response.user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Логин ---

@router.post("/login")
async def login(body: LoginRequest):
    supabase = get_supabase()
    try:
        response = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password
        })
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user_id": response.user.id
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")


# --- Получить текущего пользователя ---

@router.get("/me")
async def get_me(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)

        # Получаем подписку пользователя
        admin = get_supabase_admin()
        subscription = admin.table("subscriptions")\
            .select("*")\
            .eq("user_id", response.user.id)\
            .single()\
            .execute()

        return {
            "user_id": response.user.id,
            "email": response.user.email,
            "subscription": subscription.data
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Токен недействителен")
