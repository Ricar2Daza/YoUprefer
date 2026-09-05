from typing import List, Union, Any, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationInfo, field_validator, model_validator

class Settings(BaseSettings):
    ENV: str = "development"
    PROJECT_NAME: str = "YoUprefer"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 días
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30 # 30 días
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    # Endurecimiento JWT: issuer y audience que se incrustan en el token y se
    # validan en cada decodificación (evita tokens de otras apps/módulos).
    JWT_ISSUER: str = "youprefer-api"
    JWT_AUDIENCE: str = "youprefer-app"

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY é obrigatório. Defina a variável de ambiente SECRET_KEY.")
        return self
    
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
                    env = str(info.data.get("ENV") or "").lower()
                    if env in {"prod", "production"}:
                        raise ValueError("SQLite is not supported in production. Please use PostgreSQL.")
                    return cleaned
                return cleaned
        values = info.data
        return f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}/{values.get('POSTGRES_DB')}"

    # REDIS
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 10

    # Rate limiting. Si está habilitado, las peticiones se rechazan (429) cuando
    # se supera el límite configurado. Si Redis no está disponible, se usa
    # ``RATE_LIMIT_FAIL_OPEN`` para decidir: en False se rechaza igualmente
    # (fail-closed) y en True se deja pasar (fail-open, útil en dev).
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_FAIL_OPEN: bool = False

    # Anti brute-force en login: tras N intentos fallidos consecutivos por
    # email+IP se aplica un bloqueo con backoff exponencial (el TTL de la clave
    # de fallos crece), hasta un máximo. Se usa Redis; con el fallback in-memory
    # el contador se pierde al reiniciar (aceptable en dev).
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_BASE_SECONDS: int = 60
    LOGIN_LOCKOUT_MAX_SECONDS: int = 1800

    # Cloudflare R2 / S3
    R2_BUCKET_NAME: Optional[str] = None
    R2_ACCOUNT_ID: Optional[str] = None
    R2_ACCESS_KEY_ID: Optional[str] = None
    R2_SECRET_ACCESS_KEY: Optional[str] = None
    R2_PUBLIC_DOMAIN: Optional[str] = None # e.g. https://pub-xxx.r2.dev

    # OAuth providers
    GOOGLE_OAUTH_CLIENT_IDS: List[str] = []
    FACEBOOK_OAUTH_APP_ID: Optional[str] = None

    @field_validator("GOOGLE_OAUTH_CLIENT_IDS", mode="before")
    @classmethod
    def assemble_google_oauth_client_ids(cls, v: Union[str, List[str], None]) -> List[str]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            if v.startswith("["):
                import json
                try:
                    items = json.loads(v)
                except Exception:
                    items = [i.strip().strip('"').strip("'") for i in v.strip("[]").split(",") if i.strip().strip('"').strip("'")]
                return [str(i).strip() for i in items if str(i).strip()]
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return []

    # Servicio de email (A2). Proveedor pluggable:
    #   "log"   -> por defecto; registra el correo en el log (dev, sin credenciales)
    #   "print" -> imprime el correo renderizado en consola (útil en banda/README)
    #   "smtp"  -> envía de verdad a través de SMTP (requiere SMTP_HOST/USER/PASS)
    # EMAIL_ENABLED es el interruptor maestro; con False nada se "envía" (solo log.debug).
    EMAIL_ENABLED: bool = False
    EMAIL_PROVIDER: str = "log"
    EMAIL_FROM_NAME: str = "YoUprefer"
    EMAIL_FROM: str = "no-reply@youprefer.local"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True
    # Base del frontend para construir enlaces de recovery/verificación.
    FRONTEND_URL: str = "http://localhost:3000"

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
