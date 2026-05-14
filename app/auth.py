from fastapi import HTTPException
from app.database import get_supabase


def get_user_id(token: str) -> str:
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        return response.user.id
    except:
        raise HTTPException(status_code=401, detail="Токен недействителен")
