from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    app_env: str = "development"
    secret_key: str

    class Config:
        env_file = ".env"

settings = Settings()