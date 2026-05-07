from supabase import create_client, Client
from app.config import settings

# Клиент для операций от имени пользователя (с RLS)
def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_anon_key)

# Клиент для операций от имени сервера (обходит RLS)
def get_supabase_admin() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)