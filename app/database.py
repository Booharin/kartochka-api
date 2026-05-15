import psycopg2
import psycopg2.extras
from app.config import settings

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
