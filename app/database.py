import psycopg2
import psycopg2.extras
from app.config import settings

# Supabase клиенты (пока оставляем для совместимости)
from supabase import create_client, Client

_supabase: Client | None = None
_supabase_admin: Client | None = None

def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.supabase_url, settings.supabase_anon_key)
    return _supabase

def get_supabase_admin() -> Client:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(settings.supabase_url, settings.supabase_service_key)
    return _supabase_admin

# PostgreSQL
_pg_conn = None

def get_pg():
    global _pg_conn
    try:
        if _pg_conn is None or _pg_conn.closed:
            _pg_conn = psycopg2.connect(
                host=settings.db_host,
                port=settings.db_port,
                dbname=settings.db_name,
                user=settings.db_user,
                password=settings.db_password,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            _pg_conn.autocommit = True
    except Exception as e:
        raise Exception(f"PostgreSQL connection error: {e}")
    return _pg_conn
