from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "BOZOapp"
    environment: str = "development"
    debug: bool = False

    # Database — runtime (app connects as bozoapp_app, least-privilege)
    database_url: str
    # Database — migrations (alembic connects as owner `bozoapp` aby mohl DDL).
    # Pokud není nastaveno, fallback na database_url (pre-migration-015 chování).
    migration_database_url: str | None = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # CORS: čárkami oddělené origins (FRONTEND URL) pro produkci
    # Příklad: "https://app.bozoapp.cz,https://admin.bozoapp.cz"
    cors_origins: str = ""

    # Self-signup: povoluje POST /auth/register anonymním uživatelům. V produkci
    # BOZOapp je workflow: admin vytvoří tenant přes POST /admin/tenants.
    # Dev/test env potřebuje self-signup zapnutý pro pytest fixture.
    allow_self_signup: bool = True

    # Email (SMTP) — pokud SMTP_HOST prázdný, get_email_sender() vrátí
    # Console/Null sender (dev/test). V produkci vyžadováno.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@bozoapp.cz"
    smtp_tls: bool = True  # STARTTLS (True) / implicit TLS (False) / plaintext

    # Fernet key pro encryption-at-rest citlivých polí (personal_id atd.).
    # Generuj:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Prázdné = encryption disabled (dev/test), ale v produkci povinné.
    fernet_key: str = ""

    # Upload directory pro PDF školení a loga firem.
    # Dev: mount jako docker volume; produkce: sync na S3 (TODO: S3 wrapper).
    upload_dir: str = "/app/uploads"

    # Veřejná URL aplikace (frontend) — používá se pro odkazy v emailech
    # a v obsahu QR kódů (sken vede na /devices/{qr_token}/record).
    app_public_url: str = "http://localhost:3000"

    # Observability
    sentry_dsn: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("secret_key")
    @classmethod
    def secret_key_not_default(cls, v: str) -> str:
        """Ochrana proti zapomenuté změně default secret_key v produkci."""
        if v in ("", "change-me-generate-a-real-secret"):
            raise ValueError(
                "SECRET_KEY není nastaven nebo stále obsahuje defaultní hodnotu. "
                "Vygeneruj: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(v) < 32:
            raise ValueError("SECRET_KEY musí mít alespoň 32 znaků")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
