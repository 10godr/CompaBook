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

    app_url: str = "http://localhost:5173"
    session_days: int = 30

    # Gmail del proyecto (contraseña de aplicación). Sin ellas, en local los correos salen
    # por la consola.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_app_password: str | None = None
    email_from_name: str = "CompaBook"

    # Gemini (nivel gratuito). Los modelos están en diseno-tecnico.md §1.2; el de respaldo se usa
    # cuando el principal da 429, está caído o contesta algo inservible.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_model: str | None = "gemini-3.5-flash-lite"
    # Espera máxima por llamada a Gemini; con el respaldo, el peor caso es el doble.
    ai_timeout_seconds: float = 25.0

    # YouTube Data API v3: 10.000 unidades al día y cada búsqueda cuesta 100 (diseno-tecnico §1.3).
    youtube_api_key: str | None = None
    youtube_timeout_seconds: float = 10.0

    # Límites por usuario y día local (users.timezone); diseno-tecnico.md §2.5.
    daily_concept_limit: int = 30
    daily_retry_limit: int = 10
    # Más de 200 no cabe: lo impide un check de la base de datos.
    concept_title_max: int = 200

    # Clave del servidor para firmar (HMAC) los códigos por correo. Larga y aleatoria.
    secret_key: str | None = None
    # Secreto con el que pg_cron llama a /internal/*.
    internal_secret: str | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
