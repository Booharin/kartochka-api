from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    app_env: str = "development"
    secret_key: str = ""
    fal_key: str
    openai_api_key: str
    google_api_key: str = ""

    # PostgreSQL
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str

    # Cloudflare R2
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str
    r2_endpoint: str

    # JWT
    jwt_secret: str

    class Config:
        env_file = ".env"

settings = Settings()
