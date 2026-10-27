"""Proveedor de push: destinos permitidos, traducción de errores y que no se filtre nada."""

import json
from types import SimpleNamespace

import pytest
import requests
from pywebpush import WebPushException

from app.services import push as push_module
from app.services.push import (
    PushError,
    PushMessage,
    PushTarget,
    WebPushProvider,
    is_allowed_endpoint,
)

TARGET = PushTarget("https://web.push.apple.com/abc123", "clave-p256dh", "secreto-auth")
MESSAGE = PushMessage(title="CompaBook", body="Hola", url="/cuaderno/1", tag="repaso", ttl=120)
PRIVATE_KEY = "clave-privada-vapid"


def provider(key: str | None = PRIVATE_KEY) -> WebPushProvider:
    return WebPushProvider(key, "mailto:equipo@example.com", 7.0)


def failing(status: int | None, body: str = "texto del servicio"):
    def fake(**_: object) -> None:
        response = None if status is None else SimpleNamespace(status_code=status, text=body)
        raise WebPushException(f"fallo con {TARGET.endpoint}", response=response)

    return fake


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://web.push.apple.com/wpush/v2/abc",
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://db5p.notify.windows.com/w/?token=abc",
    ],
)
def test_los_servicios_de_push_conocidos_se_aceptan(endpoint: str) -> None:
    assert is_allowed_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "no es una url",
        "http://web.push.apple.com/abc",  # sin https
        "https://example.com/abc",
        "https://web.push.apple.com.atacante.com/abc",  # empieza igual, es otro dominio
        "https://atacante.com/web.push.apple.com",
        "https://web.push.apple.com@atacante.com/abc",  # el servidor real es lo de después de @
        "https://notify.windows.com.atacante.com/abc",
        "https://127.0.0.1/abc",
        "https://localhost/abc",
        "https://[::1/abc",  # URL mal formada
        "file:///etc/passwd",
    ],
)
def test_cualquier_otro_destino_se_rechaza(endpoint: str) -> None:
    assert not is_allowed_endpoint(endpoint)


def test_sin_claves_vapid_no_se_envia_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(push_module, "webpush", lambda **kwargs: calls.append(kwargs))
    for key in (None, ""):
        with pytest.raises(PushError) as caught:
            provider(key).send(TARGET, MESSAGE)
        assert caught.value.kind == "not_configured"
    assert calls == []


def test_un_destino_no_permitido_no_recibe_peticiones(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(push_module, "webpush", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(PushError) as caught:
        provider().send(PushTarget("https://example.com/x", "k", "a"), MESSAGE)
    assert caught.value.kind == "rejected"
    assert calls == []


def test_el_envio_lleva_la_suscripcion_el_mensaje_las_claves_y_los_limites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(push_module, "webpush", lambda **kwargs: calls.append(kwargs))
    provider().send(TARGET, MESSAGE)
    (call,) = calls
    assert call["subscription_info"] == {
        "endpoint": TARGET.endpoint,
        "keys": {"p256dh": "clave-p256dh", "auth": "secreto-auth"},
    }
    assert json.loads(call["data"]) == {
        "title": "CompaBook",
        "body": "Hola",
        "url": "/cuaderno/1",
        "tag": "repaso",
    }
    assert call["vapid_private_key"] == PRIVATE_KEY
    assert call["vapid_claims"] == {"sub": "mailto:equipo@example.com"}
    assert call["ttl"] == 120
    assert call["timeout"] == 7.0


def test_sin_etiqueta_el_aviso_no_la_lleva(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(push_module, "webpush", lambda **kwargs: calls.append(kwargs))
    provider().send(TARGET, PushMessage(title="CompaBook", body="Hola"))
    assert "tag" not in json.loads(calls[0]["data"])
    assert json.loads(calls[0]["data"])["url"] == "/"


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (404, "expired"),
        (410, "expired"),
        (429, "unavailable"),
        (500, "unavailable"),
        (503, "unavailable"),
        (None, "unavailable"),
        (400, "rejected"),
        (401, "rejected"),
        (403, "rejected"),
        (413, "rejected"),
    ],
)
def test_el_codigo_del_servicio_se_traduce_a_un_tipo_de_fallo(
    monkeypatch: pytest.MonkeyPatch, status: int | None, kind: str
) -> None:
    monkeypatch.setattr(push_module, "webpush", failing(status))
    with pytest.raises(PushError) as caught:
        provider().send(TARGET, MESSAGE)
    assert caught.value.kind == kind


@pytest.mark.parametrize("error", [requests.ConnectionError("x"), requests.Timeout("x")])
def test_un_fallo_de_red_es_pasajero(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def fake(**_: object) -> None:
        raise error

    monkeypatch.setattr(push_module, "webpush", fake)
    with pytest.raises(PushError) as caught:
        provider().send(TARGET, MESSAGE)
    assert caught.value.kind == "unavailable"


def test_el_error_no_arrastra_ni_el_endpoint_ni_las_claves_ni_el_cuerpo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_body = "cuerpo-secreto-del-servicio"
    monkeypatch.setattr(push_module, "webpush", failing(400, secret_body))
    with pytest.raises(PushError) as caught:
        provider().send(TARGET, MESSAGE)
    assert str(caught.value) == "rejected"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__

    def broken(**_: object) -> None:
        raise ValueError(f"clave mal formada: {PRIVATE_KEY}")

    monkeypatch.setattr(push_module, "webpush", broken)
    with pytest.raises(PushError) as caught:
        provider().send(TARGET, MESSAGE)
    assert caught.value.kind == "rejected"
    assert PRIVATE_KEY not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
