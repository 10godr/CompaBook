from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # En Vercel las variables vienen del entorno; en local, de backend/.env.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        extra="ignore",
    )

    database_url: str | None = None
    database_url_direct: str | None = None
    # Solo en local se desactiva Secure, porque http://localhost no es HTTPS.
    cookie_secure: bool = True

    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    # Los servicios de push exigen un contacto: un mailto: o una URL https.
    vapid_subject: str = "https://compabook.vercel.app"


@lru_cache
def get_settings() -> Settings:
    return Settings()
