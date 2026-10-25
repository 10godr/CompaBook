"""El proveedor de YouTube: la petición, los errores y la validación de lo que llega."""

import logging

import httpx
import pytest

from app.config import get_settings
from app.services.youtube import (
    Video,
    VideoError,
    YouTubeProvider,
    get_video_provider,
    parse_videos,
)

KEY = "clave-youtube-xyz"
QUERY = "qué es CI/CD explicado"
THUMB = "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"


def item(
    number: int = 1,
    title: str = "Qué es CI/CD",
    channel: str | None = "Canal",
    thumbnails: object = None,
    video_id: object = None,
) -> dict:
    ident = f"video{number:06d}"[-11:]  # 11 caracteres
    snippet: dict = {
        "title": title,
        "thumbnails": thumbnails
        if thumbnails is not None
        else {"high": {"url": f"https://i.ytimg.com/vi/{ident}/hqdefault.jpg"}},
    }
    if channel is not None:
        snippet["channelTitle"] = channel
    return {"id": {"videoId": ident if video_id is None else video_id}, "snippet": snippet}


def reply(*items: object) -> httpx.Response:
    return httpx.Response(200, json={"items": list(items)})


def status(code: int, text: str = "") -> httpx.Response:
    return httpx.Response(code, text=text)


def quota_error(reason: str, code: int = 403) -> httpx.Response:
    return httpx.Response(code, json={"error": {"errors": [{"reason": reason}]}})


class YouTube:
    """Transporte simulado: responde con lo que se le dé y anota cada petición."""

    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def provider(self, api_key: str | None = KEY) -> YouTubeProvider:
        return YouTubeProvider(api_key, transport=httpx.MockTransport(self))


# --- La petición ---------------------------------------------------------------------------


def test_devuelve_los_dos_primeros_videos() -> None:
    youtube = YouTube(reply(item(1), item(2), item(3), item(4), item(5)))
    videos = youtube.provider().search(QUERY, "es")
    assert [video.youtube_id for video in videos] == ["video000001", "video000002"]
    assert videos[0] == Video(
        "video000001",
        "Qué es CI/CD",
        "Canal",
        "https://i.ytimg.com/vi/video000001/hqdefault.jpg",
    )


def test_la_peticion_lleva_los_parametros_del_diseno_y_la_clave_en_la_cabecera() -> None:
    youtube = YouTube(reply(item()))
    youtube.provider().search(QUERY, "es")
    request = youtube.requests[0]
    assert request.method == "GET"
    assert request.url.path.endswith("/youtube/v3/search")
    assert dict(request.url.params) == {
        "part": "snippet",
        "type": "video",
        "q": QUERY,
        "relevanceLanguage": "es",
        "videoEmbeddable": "true",
        "safeSearch": "moderate",
        "maxResults": "5",
    }
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)  # las URL acaban en los logs


@pytest.mark.parametrize("language", ["es", "en"])
def test_pide_el_idioma_del_usuario(language: str) -> None:
    youtube = YouTube(reply(item()))
    youtube.provider().search(QUERY, language)
    assert youtube.requests[0].url.params["relevanceLanguage"] == language


def test_la_consulta_se_limpia_y_se_recorta() -> None:
    youtube = YouTube(reply(item()))
    youtube.provider().search("  una   consulta \n con  espacios " + "x" * 200, "es")
    sent = youtube.requests[0].url.params["q"]
    assert sent.startswith("una consulta con espacios x")
    assert len(sent) == 100


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_sin_consulta_no_se_gasta_cupo(query: str) -> None:
    youtube = YouTube(reply(item()))
    assert youtube.provider().search(query, "es") == []
    assert youtube.requests == []


def test_sin_clave_no_hace_ninguna_peticion() -> None:
    youtube = YouTube(reply(item()))
    with pytest.raises(VideoError) as error:
        youtube.provider(api_key=None).search(QUERY, "es")
    assert error.value.kind == "not_configured"
    assert youtube.requests == []


def test_sin_resultados_devuelve_una_lista_vacia() -> None:
    assert YouTube(reply()).provider().search(QUERY, "es") == []


def test_un_solo_resultado_tambien_vale() -> None:
    assert len(YouTube(reply(item(1))).provider().search(QUERY, "es")) == 1


# --- Errores -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response, kind",
    [
        (quota_error("quotaExceeded"), "quota"),
        (quota_error("dailyLimitExceeded"), "quota"),
        (quota_error("rateLimitExceeded"), "quota"),
        (status(429), "quota"),
        (quota_error("keyInvalid", code=400), "rejected"),
        (quota_error("forbidden"), "rejected"),
        (status(403, "no es json"), "rejected"),
        (status(401), "rejected"),
        (status(404), "rejected"),
        (status(500), "unavailable"),
        (status(503), "unavailable"),
    ],
    ids=[
        "cupo",
        "cupo-diario",
        "ritmo",
        "429",
        "clave-mala",
        "prohibido",
        "403-sin-json",
        "401",
        "404",
        "500",
        "503",
    ],
)
def test_clasifica_el_error_por_codigo_y_motivo(response: httpx.Response, kind: str) -> None:
    with pytest.raises(VideoError) as error:
        YouTube(response).provider().search(QUERY, "es")
    assert error.value.kind == kind


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectTimeout("lento"), httpx.ReadTimeout("lento"), httpx.ConnectError("sin red")],
    ids=["conexion-lenta", "lectura-lenta", "sin-red"],
)
def test_un_fallo_de_red_es_unavailable(failure: Exception) -> None:
    with pytest.raises(VideoError) as error:
        YouTube(failure).provider().search(QUERY, "es")
    assert error.value.kind == "unavailable"


@pytest.mark.parametrize(
    "response",
    [
        status(200, "no es json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"items": "nada"}),
        httpx.Response(200, json={"items": None}),
    ],
    ids=["no-json", "lista", "sin-items", "items-texto", "items-nulo"],
)
def test_una_respuesta_sin_forma_es_invalid_response(response: httpx.Response) -> None:
    with pytest.raises(VideoError) as error:
        YouTube(response).provider().search(QUERY, "es")
    assert error.value.kind == "invalid_response"


def test_un_error_nunca_lleva_la_consulta_ni_la_clave_ni_la_respuesta(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_query = "consulta-privada-123"
    # La API a veces repite la petición en el cuerpo del error.
    youtube = YouTube(status(400, f"API key {KEY} invalid for q={secret_query}"))
    with caplog.at_level(logging.DEBUG), pytest.raises(VideoError) as error:
        youtube.provider().search(secret_query, "es")
    for secret in (secret_query, KEY, "invalid for"):
        assert secret not in caplog.text
        assert secret not in str(error.value)
        assert secret not in repr(error.value)
    assert "outcome=rejected detail=400" in caplog.text


def test_registra_el_acierto_sin_contenido(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="compabook.youtube"):
        YouTube(reply(item(1, title="Titulo-secreto"))).provider().search("consulta-privada", "es")
    assert "outcome=ok detail=1" in caplog.text
    assert "consulta-privada" not in caplog.text
    assert "Titulo-secreto" not in caplog.text


# --- Lo que devuelve YouTube es un dato no fiable -------------------------------------------


def test_los_titulos_llegan_escapados_y_se_guardan_como_texto() -> None:
    raw = "Docker &amp; Kubernetes: &quot;desde cero&quot; &#39;f&aacute;cil&#39;"
    video = parse_videos({"items": [item(title=raw, channel="Tom &amp; Jerry")]})[0]
    assert video.title == "Docker & Kubernetes: \"desde cero\" 'fácil'"
    assert video.channel == "Tom & Jerry"


def test_las_etiquetas_html_del_titulo_no_se_interpretan_solo_se_guardan() -> None:
    video = parse_videos({"items": [item(title="&lt;b&gt;Hola&lt;/b&gt; &lt;script&gt;")]})[0]
    assert video.title == "<b>Hola</b> <script>"  # el frontend lo pinta como texto


def test_los_espacios_del_titulo_se_limpian_y_el_titulo_se_recorta() -> None:
    video = parse_videos({"items": [item(title="  Uno \n  dos  " + "x" * 300)]})[0]
    assert video.title.startswith("Uno dos x")
    assert len(video.title) == 200


def test_el_canal_es_opcional_y_se_recorta() -> None:
    assert parse_videos({"items": [item(channel=None)]})[0].channel is None
    assert parse_videos({"items": [item(channel="   ")]})[0].channel is None
    assert len(parse_videos({"items": [item(channel="c" * 300)]})[0].channel or "") == 100


@pytest.mark.parametrize(
    "video_id",
    ["corto", "demasiado-largo-12", "con espacio!", "<script>aaa", "áéíóúáéíóúá", "", 12345678901],
    ids=["corto", "largo", "espacio", "etiqueta", "acentos", "vacio", "numero"],
)
def test_un_id_de_video_con_forma_rara_se_descarta(video_id: object) -> None:
    assert parse_videos({"items": [item(video_id=video_id)]}) == []


def test_un_id_de_video_valido_admite_guiones_y_subrayados() -> None:
    assert parse_videos({"items": [item(video_id="a-b_C-d_E-9")]})[0].youtube_id == "a-b_C-d_E-9"


@pytest.mark.parametrize(
    "url",
    [
        "http://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",  # sin https
        "https://malo.example/x.jpg",
        "https://ytimg.com.malo.example/x.jpg",
        "https://malo-ytimg.com/x.jpg",
        "https://i.ytimg.com@malo.example/x.jpg",  # el host real es malo.example
        "javascript:alert(1)",
        "//i.ytimg.com/x.jpg",
        "data:image/png;base64,AAAA",
        "",
        "https://[::1/x.jpg",
    ],
    ids=[
        "http",
        "otro-dominio",
        "subdominio-falso",
        "sufijo-falso",
        "usuario-falso",
        "javascript",
        "sin-esquema",
        "data",
        "vacia",
        "malformada",
    ],
)
def test_una_miniatura_que_no_es_https_de_ytimg_descarta_el_video(url: str) -> None:
    assert parse_videos({"items": [item(thumbnails={"high": {"url": url}})]}) == []


def test_las_miniaturas_validas_se_prefieren_por_tamano() -> None:
    thumbnails = {
        "default": {"url": "https://i.ytimg.com/vi/a/default.jpg"},
        "medium": {"url": "https://i.ytimg.com/vi/a/mqdefault.jpg"},
        "high": {"url": "https://malo.example/high.jpg"},  # la más grande no vale: se baja
    }
    video = parse_videos({"items": [item(thumbnails=thumbnails)]})[0]
    assert video.thumbnail_url == "https://i.ytimg.com/vi/a/mqdefault.jpg"


@pytest.mark.parametrize("thumbnails", [{"high": "texto"}, {"high": {}}, {"other": {}}, "x", 5])
def test_miniaturas_sin_forma_descartan_el_video(thumbnails: object) -> None:
    assert parse_videos({"items": [item(thumbnails=thumbnails)]}) == []


@pytest.mark.parametrize("title", ["", "   ", "&nbsp;", None, 5])
def test_un_video_sin_titulo_se_descarta(title: object) -> None:
    broken = item()
    broken["snippet"]["title"] = title
    assert parse_videos({"items": [broken]}) == []


def test_un_resultado_roto_se_salta_y_no_tira_la_busqueda() -> None:
    items = [None, "texto", {}, {"id": "x"}, {"id": {}, "snippet": {}}, item(2), item(3)]
    assert [v.youtube_id for v in parse_videos({"items": items})] == ["video000002", "video000003"]


def test_los_videos_repetidos_se_cuentan_una_vez() -> None:
    items = [item(1), item(1), item(2)]
    assert [v.youtube_id for v in parse_videos({"items": items})] == ["video000001", "video000002"]


def test_los_resultados_rotos_no_ocupan_un_sitio_de_los_dos() -> None:
    items = [item(1, title=""), item(2), item(3), item(4)]
    assert [v.youtube_id for v in parse_videos({"items": items})] == ["video000002", "video000003"]


# --- Configuración -------------------------------------------------------------------------


def test_el_proveedor_sale_de_la_configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("YOUTUBE_TIMEOUT_SECONDS", "7")
    get_settings.cache_clear()
    try:
        provider = get_video_provider()
        assert isinstance(provider, YouTubeProvider)
        assert (provider.api_key, provider.timeout) == ("clave-de-prueba", 7.0)
    finally:
        get_settings.cache_clear()
