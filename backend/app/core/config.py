from typing import List, Union, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationInfo, field_validator, model_validator

class Settings(BaseSettings):
    ENV: str = "development"
    PROJECT_NAME: str = "YoUprefer"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 días
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30 # 30 días
    SECRET_KEY: str = "super-secret-key-change-this-in-env" # Cambiar esto en producción
    ALGORITHM: str = "HS256"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.ENV.lower() in {"prod", "production"} and self.SECRET_KEY == "super-secret-key-change-this-in-env":
            raise ValueError("SECRET_KEY must be set in production")
        return self
    
    # Base de Datos
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "carometro"
    DATABASE_URL: str | None = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, info: ValidationInfo) -> Any:
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="ignore")
        if isinstance(v, str):
            cleaned = v.strip().strip("\ufeff").strip('"').strip("'")
            if cleaned:
                if cleaned.startswith("sqlite"):
                    env = str(info.data.get("ENV") or "").lower()
                    if env in {"prod", "production"}:
                        raise ValueError("SQLite is not supported in production. Please use PostgreSQL.")
                return cleaned
        values = info.data
        return f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}/{values.get('POSTGRES_DB')}"

    # REDIS
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # Cloudflare R2 / S3
    R2_BUCKET_NAME: str | None = None
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_PUBLIC_DOMAIN: str | None = None # e.g. https://pub-xxx.r2.dev

    BACKEND_CORS_ORIGINS: List[str] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("["):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    return [i.strip().strip('"').strip("'") for i in v.strip("[]").split(",") if i.strip().strip('"').strip("'")]
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        raise ValueError(v)

    model_config = SettingsConfigDict(
        case_sensitive=True, 
        env_file=".env",
        extra="ignore"
    )

settings = Settings()
