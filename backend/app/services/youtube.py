"""La búsqueda de videos, detrás de una interfaz (VideoProvider), y la validación de lo que llega.

Se habla con la YouTube Data API v3 por REST con httpx. Lo que devuelve YouTube es texto de un
tercero: los títulos llegan escapados como HTML y cualquier campo puede venir raro, así que se
limpia y se valida todo antes de guardarlo (diseno-tecnico.md §1.3 y §5.4).
"""

import html
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx

from app.config import get_settings

logger = logging.getLogger("compabook.youtube")
# httpx registra en INFO cada petición con su URL completa, y aquí la consulta de búsqueda va en la
# URL (query string): acabaría en los logs. Con WARNING solo quedan los avisos y los errores.
logging.getLogger("httpx").setLevel(logging.WARNING)

YOUTUBE_URL = "https://www.googleapis.com/youtube/v3"
CONNECT_TIMEOUT_SECONDS = 5.0
QUERY_MAX = 100
VIDEOS_KEPT = 2
RESULTS_ASKED = 5
TITLE_MAX = 200
CHANNEL_MAX = 100
YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
THUMBNAIL_SIZES = ("high", "medium", "default")
QUOTA_REASONS = {
    "quotaExceeded",
    "dailyLimitExceeded",
    "rateLimitExceeded",
    "userRateLimitExceeded",
}

# quota: cupo del día agotado (o 429). unavailable: caído, lento o sin red. invalid_response:
# contestó algo que no sirve. rejected: el servicio no quiso hacerlo (clave o petición mal).
VideoErrorKind = Literal["quota", "unavailable", "invalid_response", "rejected", "not_configured"]


class VideoError(Exception):
    """Fallo de la búsqueda. Solo lleva el tipo: nunca la consulta, la respuesta ni la clave."""

    def __init__(self, kind: VideoErrorKind) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class Video:
    youtube_id: str
    title: str
    channel: str | None
    thumbnail_url: str


class VideoProvider(Protocol):
    def search(self, query: str, language: str) -> list[Video]:
        """Hasta 2 videos de `query` en `language` (puede ser ninguno) o lanza `VideoError`."""
        ...


# --- Validar lo que devuelve YouTube -------------------------------------------------------


def _clean(value: Any, limit: int) -> str | None:
    """Texto sin escapes HTML, con espacios colapsados y recortado; None si no queda nada."""
    if not isinstance(value, str):
        return None
    text = " ".join(html.unescape(value).split())
    return text[:limit].rstrip() or None


def _is_ytimg(url: str) -> bool:
    """Solo https y solo el dominio de miniaturas de YouTube: la web las carga en una `<img>`."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return False
    return parts.scheme == "https" and (host == "ytimg.com" or host.endswith(".ytimg.com"))


def _thumbnail(snippet: dict[str, Any]) -> str | None:
    thumbnails = snippet.get("thumbnails")
    if not isinstance(thumbnails, dict):
        return None
    for size in THUMBNAIL_SIZES:
        entry = thumbnails.get(size)
        url = entry.get("url") if isinstance(entry, dict) else None
        if isinstance(url, str) and _is_ytimg(url):
            return url
    return None


def _video(item: Any) -> Video | None:
    """Un resultado válido o None: el que no lo es se salta sin tirar la búsqueda."""
    if not isinstance(item, dict):
        return None
    ident, snippet = item.get("id"), item.get("snippet")
    video_id = ident.get("videoId") if isinstance(ident, dict) else None
    if not isinstance(snippet, dict) or not isinstance(video_id, str):
        return None
    if not YOUTUBE_ID.fullmatch(video_id):
        return None
    title = _clean(snippet.get("title"), TITLE_MAX)
    thumbnail = _thumbnail(snippet)
    if title is None or thumbnail is None:
        return None
    return Video(video_id, title, _clean(snippet.get("channelTitle"), CHANNEL_MAX), thumbnail)


def parse_videos(data: Any) -> list[Video]:
    """Los primeros 2 videos válidos y distintos de la respuesta de `search.list`."""
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise VideoError("invalid_response")
    videos: list[Video] = []
    for item in items:
        video = _video(item)
        if video and all(video.youtube_id != seen.youtube_id for seen in videos):
            videos.append(video)
        if len(videos) == VIDEOS_KEPT:
            break
    return videos


# --- YouTube -------------------------------------------------------------------------------


class YouTubeProvider:
    def __init__(
        self,
        api_key: str | None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        base_url: str = YOUTUBE_URL,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport  # los tests pasan uno simulado
        self.base_url = base_url

    def search(self, query: str, language: str) -> list[Video]:
        if not self.api_key:
            raise VideoError("not_configured")
        text = " ".join(query.split())[:QUERY_MAX]
        if not text:
            return []  # sin nada que buscar no se gasta cupo
        params = {
            "part": "snippet",
            "type": "video",
            "q": text,
            "relevanceLanguage": language,
            "videoEmbeddable": "true",
            "safeSearch": "moderate",
            "maxResults": str(RESULTS_ASKED),
        }
        started = time.monotonic()
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT_SECONDS),
            ) as client:
                response = client.get(
                    f"{self.base_url}/search",
                    # La clave va en una cabecera, no en la URL: las URL acaban en los logs.
                    headers={"x-goog-api-key": self.api_key},
                    params=params,
                )
        except httpx.HTTPError as error:
            self._log(started, "unavailable", type(error).__name__)
            raise VideoError("unavailable") from None

        if response.status_code != 200:
            kind = self._kind_of_error(response)
            self._log(started, kind, str(response.status_code))
            raise VideoError(kind)
        try:
            videos = parse_videos(response.json())
        except (ValueError, VideoError):
            self._log(started, "invalid_response", "200")
            raise VideoError("invalid_response") from None
        self._log(started, "ok", f"{len(videos)}")
        return videos

    @staticmethod
    def _kind_of_error(response: httpx.Response) -> VideoErrorKind:
        status = response.status_code
        if status == 429:
            return "quota"
        if status >= 500:
            return "unavailable"
        if status == 403 and _reason(response) in QUOTA_REASONS:
            return "quota"
        return "rejected"  # 400, 401, 403, 404: clave o petición mal

    @staticmethod
    def _log(started: float, outcome: str, detail: str) -> None:
        # Solo números y nombres: nada de la consulta, de la respuesta ni de la clave.
        elapsed_ms = int((time.monotonic() - started) * 1000)
        level = logging.INFO if outcome == "ok" else logging.WARNING
        logger.log(level, "youtube outcome=%s detail=%s ms=%d", outcome, detail, elapsed_ms)


def _reason(response: httpx.Response) -> str | None:
    """El motivo del error de la API (p. ej. `quotaExceeded`), si lo trae."""
    try:
        reason = response.json()["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return reason if isinstance(reason, str) else None


def get_video_provider() -> VideoProvider:
    settings = get_settings()
    return YouTubeProvider(settings.youtube_api_key, settings.youtube_timeout_seconds)
