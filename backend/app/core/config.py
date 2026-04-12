from typing import List, Union, Any, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationInfo, field_validator

class Settings(BaseSettings):
    PROJECT_NAME: str = "YoUprefer"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 días
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30 # 30 días
    SECRET_KEY: str = "super-secret-key-change-this-in-env" # Cambiar esto en producción
    ALGORITHM: str = "HS256"
    
    # Base de Datos
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "carometro"
    ALLOW_SQLITE: bool = False
    DATABASE_URL: Optional[str] = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> Any:
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="ignore")
        if isinstance(v, str):
            cleaned = v.strip().strip("\ufeff").strip('"').strip("'")
            if cleaned:
                if cleaned.startswith("sqlite"):
                    if info.data.get("ALLOW_SQLITE"):
                        return cleaned
                    raise ValueError("SQLite is not supported. Please use PostgreSQL.")
                return cleaned
        values = info.data
        return f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}/{values.get('POSTGRES_DB')}"

    # REDIS
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # Cloudflare R2 / S3
    R2_BUCKET_NAME: Optional[str] = None
    R2_ACCOUNT_ID: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_PUBLIC_DOMAIN: Optional[str] = None # e.g. https://pub-xxx.r2.dev

    BACKEND_CORS_ORIGINS: List[str] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("["):
                import json
                try:
                    items = json.loads(v)
                except Exception:
                    items = [i.strip().strip('"').strip("'") for i in v.strip("[]").split(",") if i.strip().strip('"').strip("'")]
                return [str(i).strip().rstrip("/") for i in items if str(i).strip()]
            return [i.strip().rstrip("/") for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip().rstrip("/") for i in v if str(i).strip()]
        raise ValueError(v)

    model_config = SettingsConfigDict(
        case_sensitive=True, 
        env_file=".env",
        extra="ignore"
    )

settings = Settings()
