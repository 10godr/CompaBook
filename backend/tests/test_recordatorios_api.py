"""API de recordatorios y push (Fase 7): ajustes, dispositivos, aviso de prueba y aislamiento."""

import logging
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.services.push import PushError
from tests.helpers import (
    HEADERS,
    FakeEmailProvider,
    FakePushProvider,
    invite,
    register,
    signup,
    token_of,
    verify,
)

BETO = "beto@example.com"
CAROL = "carol@example.com"
APPLE = "https://web.push.apple.com/wpush/v2/ana-iphone"
GOOGLE = "https://fcm.googleapis.com/fcm/send/ana-android"
KEYS = {"p256dh": "clave-p256dh-de-prueba", "auth": "secreto-auth-de-prueba"}
DEFAULTS = {
    "enabled": False,
    "local_time": "20:00",
    "weekdays": [1, 2, 3, 4, 5, 6, 7],
    "timezone": "America/Santo_Domingo",
    "devices": 0,
}


def auth(token: str) -> dict[str, str]:
    return {**HEADERS, "Cookie": f"cb_session={token}"}


def get_reminders(client: TestClient, token: str):
    return client.get("/api/v1/reminders", headers=auth(token))


def put_reminders(client: TestClient, token: str, **override: object):
    body = {"enabled": True, "local_time": "07:30", "weekdays": [1, 3, 5], **override}
    return client.put("/api/v1/reminders", json=body, headers=auth(token))


def subscribe(client: TestClient, token: str, endpoint: str = APPLE, **override: object):
    return client.post(
        "/api/v1/push/subscriptions",
        json={"endpoint": endpoint, "keys": KEYS, **override},
        headers=auth(token),
    )


def unsubscribe(client: TestClient, token: str, endpoint: str = APPLE):
    return client.request(
        "DELETE", "/api/v1/push/subscriptions", json={"endpoint": endpoint}, headers=auth(token)
    )


def send_test(client: TestClient, token: str, **body: object):
    return client.post("/api/v1/push/test", json=body, headers=auth(token))


def devices(client: TestClient, token: str) -> int:
    return get_reminders(client, token).json()["devices"]


@pytest.fixture
def ana(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> str:
    return token_of(signup(client, orm, mailer))


@pytest.fixture
def beto(client: TestClient, orm: DbSession, mailer: FakeEmailProvider, ana: str) -> str:
    return token_of(signup(client, orm, mailer, email=BETO))


@pytest.fixture
def carol_en(client: TestClient, orm: DbSession, mailer: FakeEmailProvider, ana: str) -> str:
    invite(orm, CAROL)
    register(client, email=CAROL, language="en")
    return token_of(verify(client, mailer.last_code(), CAROL))


# --- Ajustes -------------------------------------------------------------------------------


def test_sin_guardar_nada_valen_los_ajustes_de_fabrica(client: TestClient, ana: str) -> None:
    response = get_reminders(client, ana)
    assert response.status_code == 200
    assert response.json() == DEFAULTS


def test_guardar_los_ajustes_y_leerlos(client: TestClient, ana: str) -> None:
    response = put_reminders(client, ana)
    assert response.status_code == 200
    expected = {**DEFAULTS, "enabled": True, "local_time": "07:30", "weekdays": [1, 3, 5]}
    assert response.json() == expected
    assert get_reminders(client, ana).json() == expected


def test_los_dias_se_devuelven_ordenados_y_sin_repetir(client: TestClient, ana: str) -> None:
    response = put_reminders(client, ana, weekdays=[7, 1, 7, 3, 1])
    assert response.json()["weekdays"] == [1, 3, 7]


def test_se_pueden_apagar_los_recordatorios_sin_perder_la_hora_ni_los_dias(
    client: TestClient, ana: str
) -> None:
    put_reminders(client, ana)
    response = put_reminders(client, ana, enabled=False, local_time="07:30", weekdays=[1, 3, 5])
    assert response.json()["enabled"] is False
    assert get_reminders(client, ana).json()["local_time"] == "07:30"


@pytest.mark.parametrize("local_time", ["", "7:30", "25:00", "20:60", "20:00:00", "ab:cd", "2000"])
def test_una_hora_que_no_es_hh_mm_se_rechaza(client: TestClient, ana: str, local_time: str) -> None:
    response = put_reminders(client, ana, local_time=local_time)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert get_reminders(client, ana).json() == DEFAULTS


@pytest.mark.parametrize("weekdays", [[], [0], [8], [1, 8], [-1], list(range(1, 9)), ["lunes"]])
def test_los_dias_deben_ser_de_1_a_7_y_haber_alguno(
    client: TestClient, ana: str, weekdays: list[object]
) -> None:
    response = put_reminders(client, ana, weekdays=weekdays)
    assert response.status_code == 422
    assert get_reminders(client, ana).json() == DEFAULTS


def test_faltan_campos(client: TestClient, ana: str) -> None:
    response = client.put("/api/v1/reminders", json={"enabled": True}, headers=auth(ana))
    assert response.status_code == 422


def test_guardar_con_la_zona_del_dispositivo_actualiza_la_zona_de_la_cuenta(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    response = put_reminders(client, ana, timezone="Europe/Madrid")
    assert response.json()["timezone"] == "Europe/Madrid"
    zone = orm.execute(text("select timezone from users where email = 'ana@example.com'"))
    assert zone.scalar_one() == "Europe/Madrid"
    assert client.get("/api/v1/me", headers=auth(ana)).json()["user"]["timezone"] == "Europe/Madrid"


def test_sin_zona_en_la_peticion_la_cuenta_conserva_la_suya(client: TestClient, ana: str) -> None:
    assert put_reminders(client, ana).json()["timezone"] == "America/Santo_Domingo"


def test_una_zona_desconocida_se_rechaza_y_no_se_guarda_nada(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    response = put_reminders(client, ana, timezone="Marte/Olympus")
    assert response.status_code == 422
    assert get_reminders(client, ana).json() == DEFAULTS
    zone = orm.execute(text("select timezone from users where email = 'ana@example.com'"))
    assert zone.scalar_one() == "America/Santo_Domingo"


def test_guardar_no_borra_el_ultimo_envio(client: TestClient, orm: DbSession, ana: str) -> None:
    put_reminders(client, ana)
    orm.execute(text("update reminder_settings set last_sent_on = '2026-10-24'"))
    put_reminders(client, ana, local_time="21:00")
    assert orm.execute(text("select last_sent_on::text from reminder_settings")).scalar_one() == (
        "2026-10-24"
    )


def test_cada_usuario_ve_y_cambia_solo_lo_suyo(client: TestClient, ana: str, beto: str) -> None:
    put_reminders(client, ana, local_time="07:30")
    assert get_reminders(client, beto).json() == DEFAULTS
    put_reminders(client, beto, local_time="22:15", enabled=False)
    assert get_reminders(client, ana).json()["local_time"] == "07:30"
    assert get_reminders(client, ana).json()["enabled"] is True


# --- Dispositivos --------------------------------------------------------------------------


def test_suscribir_un_dispositivo_lo_cuenta(client: TestClient, ana: str) -> None:
    response = subscribe(client, ana)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert devices(client, ana) == 1


def test_se_guarda_el_dispositivo_con_su_navegador(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    client.post(
        "/api/v1/push/subscriptions",
        json={"endpoint": APPLE, "keys": KEYS},
        headers={**auth(ana), "User-Agent": "Mozilla/5.0 " + "x" * 600},
    )
    agent = orm.execute(text("select user_agent from push_subscriptions")).scalar_one()
    assert agent.startswith("Mozilla/5.0 ") and len(agent) == 512


def test_suscribir_dos_veces_el_mismo_dispositivo_no_lo_duplica(
    client: TestClient, ana: str
) -> None:
    subscribe(client, ana)
    subscribe(client, ana)
    assert devices(client, ana) == 1


def test_un_usuario_puede_tener_varios_dispositivos(client: TestClient, ana: str) -> None:
    subscribe(client, ana, APPLE)
    subscribe(client, ana, GOOGLE)
    assert devices(client, ana) == 2


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://web.push.apple.com/abc",
        "https://example.com/abc",
        "https://web.push.apple.com.atacante.com/abc",
        "https://127.0.0.1/abc",
        "no es una url",
    ],
)
def test_solo_se_aceptan_los_servicios_de_push_conocidos(
    client: TestClient, orm: DbSession, ana: str, endpoint: str
) -> None:
    response = subscribe(client, ana, endpoint)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["fields"] == [{"field": "endpoint", "type": "value_error"}]
    assert orm.execute(text("select count(*) from push_subscriptions")).scalar_one() == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"endpoint": "", "keys": KEYS},
        {"endpoint": APPLE + "x" * 2049, "keys": KEYS},
        {"endpoint": APPLE},
        {"endpoint": APPLE, "keys": {"p256dh": "k"}},
        {"endpoint": APPLE, "keys": {"p256dh": "", "auth": "a"}},
        {"endpoint": APPLE, "keys": {"p256dh": "k" * 513, "auth": "a"}},
        {"keys": KEYS},
    ],
)
def test_una_suscripcion_incompleta_o_desmedida_se_rechaza(
    client: TestClient, ana: str, payload: dict[str, object]
) -> None:
    response = client.post("/api/v1/push/subscriptions", json=payload, headers=auth(ana))
    assert response.status_code == 422
    assert devices(client, ana) == 0


def test_el_error_de_validacion_no_repite_el_endpoint_ni_las_claves(
    client: TestClient, ana: str
) -> None:
    response = subscribe(client, ana, "https://example.com/mi-endpoint-secreto")
    assert "mi-endpoint-secreto" not in response.text
    assert KEYS["auth"] not in response.text


def test_un_dispositivo_pasa_al_ultimo_usuario_que_se_suscribe(
    client: TestClient, ana: str, beto: str
) -> None:
    subscribe(client, ana)
    assert devices(client, ana) == 1
    subscribe(client, beto)
    assert devices(client, ana) == 0
    assert devices(client, beto) == 1


def test_hay_un_maximo_de_cinco_dispositivos_y_se_descarta_el_mas_viejo(
    client: TestClient, clock: dict[str, datetime], ana: str
) -> None:
    endpoints = [f"https://web.push.apple.com/wpush/{n}" for n in range(6)]
    for endpoint in endpoints:
        clock["now"] += timedelta(minutes=1)
        subscribe(client, ana, endpoint)
    assert devices(client, ana) == 5
    assert unsubscribe(client, ana, endpoints[0]).status_code == 404  # el más viejo ya no está
    assert unsubscribe(client, ana, endpoints[5]).status_code == 200


def test_dar_de_baja_el_dispositivo(client: TestClient, ana: str) -> None:
    subscribe(client, ana)
    response = unsubscribe(client, ana)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert devices(client, ana) == 0


def test_dar_de_baja_dos_veces_o_uno_que_no_existe_da_404(client: TestClient, ana: str) -> None:
    subscribe(client, ana)
    unsubscribe(client, ana)
    again = unsubscribe(client, ana)
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "not_found"


def test_no_se_puede_dar_de_baja_el_dispositivo_de_otro_usuario(
    client: TestClient, ana: str, beto: str
) -> None:
    subscribe(client, ana)
    response = unsubscribe(client, beto)
    assert response.status_code == 404
    inexistente = unsubscribe(client, beto, APPLE + "-otro")
    assert response.json() == inexistente.json()  # un dispositivo ajeno es como uno inexistente
    assert devices(client, ana) == 1


def test_dar_de_baja_sin_indicar_cual_es_un_error_de_validacion(
    client: TestClient, ana: str
) -> None:
    response = client.request("DELETE", "/api/v1/push/subscriptions", headers=auth(ana))
    assert response.status_code == 422


# --- Clave pública -------------------------------------------------------------------------


def test_la_clave_publica_se_pide_sin_sesion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "vapid_public_key", "clave-publica-de-prueba")
    response = client.get("/api/v1/push/vapid-public-key")
    assert response.status_code == 200
    assert response.json() == {"public_key": "clave-publica-de-prueba"}


def test_sin_clave_publica_configurada_responde_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "vapid_public_key", None)
    response = client.get("/api/v1/push/vapid-public-key")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "push_unavailable"


# --- Aviso de prueba -----------------------------------------------------------------------


def test_el_aviso_de_prueba_llega_al_dispositivo_indicado(
    client: TestClient, ana: str, push: FakePushProvider
) -> None:
    subscribe(client, ana, APPLE)
    subscribe(client, ana, GOOGLE)
    response = send_test(client, ana, endpoint=GOOGLE)
    assert response.status_code == 200
    assert response.json() == {"sent": 1, "expired": 0, "failed": 0}
    ((target, message),) = push.sent
    assert (target.endpoint, target.p256dh, target.auth) == (GOOGLE, KEYS["p256dh"], KEYS["auth"])
    assert message.title == "CompaBook"
    assert message.body == "Las notificaciones funcionan en este dispositivo."
    assert (message.url, message.tag, message.ttl) == ("/", "test", 60)


def test_sin_indicar_dispositivo_el_aviso_va_a_todos_los_del_usuario(
    client: TestClient, ana: str, beto: str, push: FakePushProvider
) -> None:
    subscribe(client, ana, APPLE)
    subscribe(client, ana, GOOGLE)
    subscribe(client, beto, "https://web.push.apple.com/wpush/v2/beto")
    assert send_test(client, ana).json() == {"sent": 2, "expired": 0, "failed": 0}
    assert {target.endpoint for target, _ in push.sent} == {APPLE, GOOGLE}


def test_el_aviso_de_prueba_sale_en_el_idioma_de_la_cuenta(
    client: TestClient, carol_en: str, push: FakePushProvider
) -> None:
    subscribe(client, carol_en)
    send_test(client, carol_en)
    assert push.sent[0][1].body == "Notifications are working on this device."


def test_sin_dispositivos_no_hay_a_quien_avisar(
    client: TestClient, orm: DbSession, ana: str, push: FakePushProvider
) -> None:
    response = send_test(client, ana)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_devices"
    assert push.sent == []
    events = orm.execute(text("select count(*) from rate_limit_events where bucket = 'push_test'"))
    assert events.scalar_one() == 0  # no hubo nada que limitar


def test_no_se_puede_avisar_a_un_dispositivo_ajeno_inexistente_o_inactivo(
    client: TestClient, ana: str, beto: str, push: FakePushProvider
) -> None:
    subscribe(client, beto, "https://web.push.apple.com/wpush/v2/beto")
    subscribe(client, ana, APPLE)
    push.errors[APPLE] = PushError("expired")
    assert send_test(client, ana, endpoint=APPLE).json()["expired"] == 1  # ahora está inactivo
    push.errors.clear()
    for endpoint in (
        "https://web.push.apple.com/wpush/v2/beto",  # de otro usuario
        "https://web.push.apple.com/wpush/v2/no-existe",
        APPLE,  # propio pero inactivo
    ):
        response = send_test(client, ana, endpoint=endpoint)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert push.sent == []


def test_un_dispositivo_caducado_se_da_de_baja(
    client: TestClient, ana: str, push: FakePushProvider
) -> None:
    subscribe(client, ana, APPLE)
    subscribe(client, ana, GOOGLE)
    push.errors[APPLE] = PushError("expired")
    assert send_test(client, ana).json() == {"sent": 1, "expired": 1, "failed": 0}
    assert devices(client, ana) == 1


def test_un_fallo_pasajero_no_da_de_baja_el_dispositivo(
    client: TestClient, ana: str, push: FakePushProvider
) -> None:
    subscribe(client, ana)
    push.error = PushError("unavailable")
    assert send_test(client, ana).json() == {"sent": 0, "expired": 0, "failed": 1}
    assert devices(client, ana) == 1


def test_sin_claves_vapid_el_aviso_de_prueba_responde_503(
    client: TestClient, ana: str, push: FakePushProvider
) -> None:
    subscribe(client, ana)
    push.error = PushError("not_configured")
    response = send_test(client, ana)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "push_unavailable"


def test_el_aviso_de_prueba_tiene_limite_por_usuario_y_hora(
    client: TestClient, clock: dict[str, datetime], ana: str, beto: str, push: FakePushProvider
) -> None:
    subscribe(client, ana)
    subscribe(client, beto, "https://web.push.apple.com/wpush/v2/beto")
    for _ in range(5):
        assert send_test(client, ana).status_code == 200
    blocked = send_test(client, ana)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.json()["error"]["retry_after"] > 0
    assert len(push.sent) == 5
    assert send_test(client, beto).status_code == 200  # el límite es de cada usuario
    clock["now"] += timedelta(hours=1, seconds=1)
    assert send_test(client, ana).status_code == 200


def test_ni_el_endpoint_ni_las_claves_ni_el_texto_llegan_a_los_registros(
    client: TestClient, ana: str, push: FakePushProvider, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    subscribe(client, ana)
    push.error = PushError("expired")
    send_test(client, ana)
    subscribe(client, ana)
    push.error = PushError("unavailable")
    send_test(client, ana)
    logs = caplog.text
    assert "expired" in logs and "unavailable" in logs  # lo único que se anota: el tipo
    for secret in (APPLE, "ana-iphone", KEYS["p256dh"], KEYS["auth"], "funcionan en este"):
        assert secret not in logs


# --- Sesión y cabecera CSRF ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/reminders", None),
        ("PUT", "/api/v1/reminders", {"enabled": True, "local_time": "07:30", "weekdays": [1]}),
        ("POST", "/api/v1/push/subscriptions", {"endpoint": APPLE, "keys": KEYS}),
        ("DELETE", "/api/v1/push/subscriptions", {"endpoint": APPLE}),
        ("POST", "/api/v1/push/test", {}),
    ],
)
def test_sin_sesion_responde_401(
    client: TestClient, method: str, path: str, body: dict[str, object] | None
) -> None:
    response = client.request(method, path, json=body, headers=HEADERS)
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", "/api/v1/reminders", {"enabled": True, "local_time": "07:30", "weekdays": [1]}),
        ("POST", "/api/v1/push/subscriptions", {"endpoint": APPLE, "keys": KEYS}),
        ("DELETE", "/api/v1/push/subscriptions", {"endpoint": APPLE}),
        ("POST", "/api/v1/push/test", {}),
    ],
)
def test_sin_la_cabecera_x_requested_with_responde_403(
    client: TestClient, ana: str, method: str, path: str, body: dict[str, object]
) -> None:
    response = client.request(method, path, json=body, headers={"Cookie": f"cb_session={ana}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf"
