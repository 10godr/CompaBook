"""API de conceptos (Fase 6a): crear, procesar, reintentar, listar, límites y aislamiento."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.services.ai import AIError, GeneratedCard
from tests.helpers import (
    HEADERS,
    NOW,
    FakeAIProvider,
    FakeEmailProvider,
    invite,
    make_content,
    register,
    signup,
    token_of,
    verify,
)

BASE = "/api/v1/concepts"
BETO = "beto@example.com"
ANA_ZONE_OFFSET = timedelta(hours=-4)  # America/Santo_Domingo, la zona con la que se registra


def auth(token: str) -> dict[str, str]:
    return {**HEADERS, "Cookie": f"cb_session={token}"}


def create(client: TestClient, token: str, title: str = "CI/CD"):
    return client.post(BASE, json={"title": title}, headers=auth(token))


def process(client: TestClient, token: str, concept_id: object):
    return client.post(f"{BASE}/{concept_id}/process", headers=auth(token))


def retry(client: TestClient, token: str, concept_id: object):
    return client.post(f"{BASE}/{concept_id}/retry", headers=auth(token))


def get(client: TestClient, token: str, path: str = ""):
    return client.get(f"{BASE}{path}", headers=auth(token))


def create_and_process(client: TestClient, token: str, title: str = "CI/CD") -> str:
    concept_id = create(client, token, title).json()["id"]
    assert process(client, token, concept_id).status_code == 200
    return concept_id


def count(orm: DbSession, table: str) -> int:
    return orm.execute(text(f"select count(*) from {table}")).scalar_one()


def set_job(orm: DbSession, concept_id: str, **columns: object) -> None:
    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    orm.execute(
        text(f"update processing_jobs set {assignments} where concept_id = :concept_id"),
        {**columns, "concept_id": concept_id},
    )
    orm.flush()


def job_row(orm: DbSession, concept_id: str):
    return orm.execute(
        text(
            "select status, stage, attempts, last_error, locked_at from processing_jobs "
            "where concept_id = :id"
        ),
        {"id": concept_id},
    ).one()


@pytest.fixture
def ana(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> str:
    return token_of(signup(client, orm, mailer))


@pytest.fixture
def beto(client: TestClient, orm: DbSession, mailer: FakeEmailProvider, ana: str) -> str:
    return token_of(signup(client, orm, mailer, email=BETO))


def signup_english(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> str:
    email = "carol@example.com"
    invite(orm, email)
    register(client, email=email, language="en")
    return token_of(verify(client, mailer.last_code(), email))


# --- Crear ---


def test_crear_guarda_el_concepto_y_su_trabajo_sin_llamar_a_la_ia(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    response = create(client, ana, "  CI/CD  ")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert ai.calls == []
    assert count(orm, "concepts") == 1
    assert job_row(orm, body["id"]).status == "pending"
    assert get(client, ana, f"/{body['id']}").json()["title"] == "CI/CD"


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_un_titulo_vacio_o_demasiado_largo_se_rechaza(
    client: TestClient, orm: DbSession, ana: str, title: str
) -> None:
    response = create(client, ana, title)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert count(orm, "concepts") == 0


def test_un_titulo_de_200_caracteres_vale(client: TestClient, ana: str) -> None:
    assert create(client, ana, "x" * 200).status_code == 201


def test_sin_titulo_es_un_error_de_validacion(client: TestClient, ana: str) -> None:
    assert client.post(BASE, json={}, headers=auth(ana)).status_code == 422


def test_el_concepto_nace_en_el_idioma_del_usuario(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider, ana: str, ai: FakeAIProvider
) -> None:
    carol = signup_english(client, orm, mailer)
    create_and_process(client, ana, "Docker")
    create_and_process(client, carol, "Docker")
    assert ai.calls == [("Docker", "es"), ("Docker", "en")]


def test_el_mismo_concepto_en_dos_idiomas_son_dos_fichas(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider, ana: str
) -> None:
    carol = signup_english(client, orm, mailer)
    create_and_process(client, ana, "Docker")
    create_and_process(client, carol, "Docker")
    assert count(orm, "concept_cards") == 2


# --- Sesión y CSRF ---


def test_sin_sesion_todo_responde_401(client: TestClient) -> None:
    some_id = uuid.uuid4()
    calls = [
        client.post(BASE, json={"title": "x"}, headers=HEADERS),
        client.get(BASE),
        client.get(f"{BASE}/{some_id}"),
        client.get(f"{BASE}/{some_id}/status"),
        client.post(f"{BASE}/{some_id}/process", headers=HEADERS),
        client.post(f"{BASE}/{some_id}/retry", headers=HEADERS),
        client.delete(f"{BASE}/{some_id}", headers=HEADERS),
    ]
    assert [call.status_code for call in calls] == [401] * len(calls)


def test_las_escrituras_exigen_la_cabecera_csrf(client: TestClient, ana: str) -> None:
    concept_id = create(client, ana).json()["id"]
    cookie = {"Cookie": f"cb_session={ana}"}
    calls = [
        client.post(BASE, json={"title": "x"}, headers=cookie),
        client.post(f"{BASE}/{concept_id}/process", headers=cookie),
        client.post(f"{BASE}/{concept_id}/retry", headers=cookie),
        client.delete(f"{BASE}/{concept_id}", headers=cookie),
    ]
    assert [call.status_code for call in calls] == [403] * len(calls)
    assert get(client, ana, f"/{concept_id}").status_code == 200  # no se borró


# --- Procesar ---


def test_procesar_guarda_la_ficha_y_completa_el_trabajo(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create(client, ana, "CI/CD").json()["id"]
    response = process(client, ana, concept_id)
    assert response.status_code == 200
    assert response.json() == {"status": "completed", "stage": "done", "attempts": 0}
    assert ai.calls == [("CI/CD", "es")]
    detail = get(client, ana, f"/{concept_id}").json()
    assert detail["card"]["what_is"] == "Qué es."
    assert detail["card"]["canonical_title"] == "CI/CD"
    assert detail["card_title"] == "CI/CD"
    assert detail["videos"] == []
    assert job_row(orm, concept_id).locked_at is None


def test_la_ficha_no_expone_datos_internos(client: TestClient, ana: str) -> None:
    concept_id = create_and_process(client, ana)
    card = get(client, ana, f"/{concept_id}").json()["card"]
    assert set(card) == {
        "canonical_title",
        "what_is",
        "what_for",
        "example",
        "example_code",
        "example_code_language",
    }


def test_el_contenido_con_etiquetas_se_devuelve_tal_cual(
    client: TestClient, ana: str, ai: FakeAIProvider
) -> None:
    ai.cards["HTML"] = make_content("HTML", what_is="Usa <b>etiquetas</b> como <div>.")
    concept_id = create_and_process(client, ana, "HTML")
    assert get(client, ana, f"/{concept_id}").json()["card"]["what_is"] == (
        "Usa <b>etiquetas</b> como <div>."
    )


def test_procesar_dos_veces_no_vuelve_a_llamar_a_la_ia(
    client: TestClient, ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create_and_process(client, ana)
    again = process(client, ana, concept_id)
    assert again.status_code == 200
    assert again.json()["status"] == "completed"
    assert len(ai.calls) == 1


def test_si_otro_proceso_lo_tiene_responde_202_sin_llamar_a_la_ia(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create(client, ana).json()["id"]
    set_job(orm, concept_id, status="processing", stage="writing", locked_at=NOW)
    response = process(client, ana, concept_id)
    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    assert ai.calls == []


def test_el_trabajo_se_reclama_y_confirma_antes_de_llamar_a_la_ia(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    seen: dict[str, object] = {}

    class SpyAI(FakeAIProvider):
        def generate_card(self, title: str, language: str) -> GeneratedCard:
            seen["in_transaction"] = orm.in_transaction()
            seen["status"] = orm.execute(text("select status from processing_jobs")).scalar_one()
            return super().generate_card(title, language)

    from app.main import app
    from app.services.ai import get_ai_provider

    app.dependency_overrides[get_ai_provider] = lambda: SpyAI()
    concept_id = create(client, ana).json()["id"]
    assert process(client, ana, concept_id).status_code == 200
    # Sin transacción abierta durante la llamada, y el trabajo ya figura como tomado.
    assert seen == {"in_transaction": False, "status": "processing"}


def test_si_la_ia_falla_el_concepto_queda_guardado_y_el_trabajo_failed(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    ai.error = AIError("busy")
    concept_id = create(client, ana).json()["id"]
    response = process(client, ana, concept_id)
    assert response.status_code == 200
    assert response.json() == {"status": "failed", "stage": "writing", "attempts": 1}
    assert count(orm, "concepts") == 1
    assert count(orm, "concept_cards") == 0
    row = job_row(orm, concept_id)
    assert (row.status, row.last_error, row.locked_at) == ("failed", "busy", None)
    assert get(client, ana, f"/{concept_id}").json()["card"] is None
    assert [item["id"] for item in get(client, ana).json()["items"]] == [concept_id]


def test_una_respuesta_invalida_de_la_ia_no_guarda_ficha(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    ai.error = AIError("invalid_response")
    concept_id = create(client, ana).json()["id"]
    assert process(client, ana, concept_id).json()["status"] == "failed"
    assert count(orm, "concept_cards") == 0
    assert job_row(orm, concept_id).last_error == "invalid_response"


def test_un_fallo_inesperado_tambien_deja_el_trabajo_failed(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    ai.error = RuntimeError("algo raro")
    concept_id = create(client, ana).json()["id"]
    assert process(client, ana, concept_id).json()["status"] == "failed"
    assert job_row(orm, concept_id).last_error == "internal_error"


def test_el_mismo_slug_comparte_una_sola_ficha(
    client: TestClient, orm: DbSession, ana: str, beto: str, ai: FakeAIProvider
) -> None:
    ai.cards["CI/CD"] = make_content("CI/CD", cache_slug="ci-cd")
    ai.cards["ci cd"] = make_content("CI CD", cache_slug="ci-cd", what_is="Otra redacción.")
    first = create_and_process(client, ana, "CI/CD")
    second = create_and_process(client, beto, "ci cd")
    assert count(orm, "concept_cards") == 1
    card_ana = get(client, ana, f"/{first}").json()["card"]
    card_beto = get(client, beto, f"/{second}").json()["card"]
    assert card_ana == card_beto  # gana la primera ficha guardada


def test_el_estado_solo_trae_status_stage_y_attempts(client: TestClient, ana: str) -> None:
    concept_id = create(client, ana).json()["id"]
    response = get(client, ana, f"/{concept_id}/status")
    assert response.json() == {"status": "pending", "stage": "queued", "attempts": 0}
    process(client, ana, concept_id)
    assert get(client, ana, f"/{concept_id}/status").json() == {
        "status": "completed",
        "stage": "done",
        "attempts": 0,
    }


# --- Trabajo abandonado ---


def test_un_trabajo_processing_abandonado_se_informa_como_failed(
    client: TestClient, orm: DbSession, clock: dict[str, datetime], ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create(client, ana).json()["id"]
    set_job(orm, concept_id, status="processing", stage="writing", locked_at=NOW)
    clock["now"] = NOW + timedelta(minutes=4)
    assert get(client, ana, f"/{concept_id}/status").json()["status"] == "processing"
    clock["now"] = NOW + timedelta(minutes=6)
    assert get(client, ana, f"/{concept_id}/status").json()["status"] == "failed"
    assert get(client, ana, f"/{concept_id}").json()["status"] == "failed"
    assert get(client, ana).json()["items"][0]["status"] == "failed"
    # /process no lo retoma: hay que reintentar.
    assert process(client, ana, concept_id).json()["status"] == "failed"
    assert ai.calls == []


def test_reintentar_un_trabajo_abandonado_lo_deja_en_cola_y_se_procesa(
    client: TestClient, orm: DbSession, clock: dict[str, datetime], ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create(client, ana).json()["id"]
    set_job(orm, concept_id, status="processing", stage="writing", locked_at=NOW)
    clock["now"] = NOW + timedelta(minutes=6)
    assert retry(client, ana, concept_id).status_code == 202
    assert process(client, ana, concept_id).json()["status"] == "completed"
    assert len(ai.calls) == 1


# --- Reintentar ---


def test_reintentar_tras_un_fallo_reinicia_el_mismo_trabajo(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    ai.error = AIError("unavailable")
    concept_id = create(client, ana).json()["id"]
    process(client, ana, concept_id)
    response = retry(client, ana, concept_id)
    assert response.status_code == 202
    assert response.json() == {"status": "pending", "stage": "queued", "attempts": 0}
    ai.error = None
    assert process(client, ana, concept_id).json()["status"] == "completed"
    assert count(orm, "processing_jobs") == 1


@pytest.mark.parametrize("state", ["pending", "completed"])
def test_solo_se_reintenta_lo_que_fallo(
    client: TestClient, ana: str, state: str, ai: FakeAIProvider
) -> None:
    concept_id = create(client, ana).json()["id"]
    if state == "completed":
        process(client, ana, concept_id)
    response = retry(client, ana, concept_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_retryable"


def test_reintentar_con_la_ficha_ya_guardada_no_gasta_la_ia(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create_and_process(client, ana)
    # Como si la función muriera justo después de guardar la ficha.
    set_job(orm, concept_id, status="failed", stage="writing")
    assert retry(client, ana, concept_id).status_code == 202
    assert process(client, ana, concept_id).json()["status"] == "completed"
    assert len(ai.calls) == 1


def test_los_reintentos_tienen_limite_diario(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, ana: str, ai: FakeAIProvider
) -> None:
    monkeypatch.setattr(get_settings(), "daily_retry_limit", 2)
    ai.error = AIError("busy")
    concept_id = create(client, ana).json()["id"]
    for _ in range(2):
        process(client, ana, concept_id)
        assert retry(client, ana, concept_id).status_code == 202
    process(client, ana, concept_id)
    blocked = retry(client, ana, concept_id)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "daily_limit_reached"
    # El concepto sigue fallido: no se reinició nada.
    assert get(client, ana, f"/{concept_id}/status").json()["status"] == "failed"


# --- Límite diario ---


def test_el_concepto_numero_31_responde_429_y_no_se_crea(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    for number in range(30):
        assert create(client, ana, f"concepto {number}").status_code == 201
    response = create(client, ana, "uno más")
    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "daily_limit_reached"
    assert error["limit"] == 30
    assert count(orm, "concepts") == 30


def test_eliminar_un_concepto_no_devuelve_el_cupo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, ana: str
) -> None:
    monkeypatch.setattr(get_settings(), "daily_concept_limit", 2)
    first = create(client, ana, "uno").json()["id"]
    create(client, ana, "dos")
    assert client.delete(f"{BASE}/{first}", headers=auth(ana)).status_code == 200
    assert create(client, ana, "tres").status_code == 429


def test_el_dia_es_el_dia_local_del_usuario(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, clock: dict[str, datetime], ana: str
) -> None:
    monkeypatch.setattr(get_settings(), "daily_concept_limit", 2)
    # 19:00 del 24 en Santo Domingo (UTC-4) = 23:00 UTC del 24.
    clock["now"] = datetime(2026, 10, 24, 23, 0, tzinfo=UTC)
    create(client, ana, "uno")
    create(client, ana, "dos")
    # 21:00 locales: en UTC ya es el 25, pero para el usuario sigue siendo el mismo día.
    clock["now"] = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    blocked = create(client, ana, "tres")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["retry_after"] == 3 * 3600  # faltan 3 h para la medianoche local
    # Medianoche local (04:00 UTC): día nuevo.
    clock["now"] = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
    assert create(client, ana, "tres").status_code == 201


def test_me_informa_el_uso_del_dia(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, ana: str, beto: str
) -> None:
    monkeypatch.setattr(get_settings(), "daily_concept_limit", 5)
    assert client.get("/api/v1/me", headers=auth(ana)).json()["usage"] == {
        "concepts_today": 0,
        "daily_limit": 5,
    }
    create(client, ana, "uno")
    create(client, ana, "dos")
    create(client, beto, "otro")
    assert client.get("/api/v1/me", headers=auth(ana)).json()["usage"]["concepts_today"] == 2
    assert client.get("/api/v1/me", headers=auth(beto)).json()["usage"]["concepts_today"] == 1


# --- Listar y buscar ---


def create_many(client: TestClient, clock: dict[str, datetime], token: str, titles: list[str]):
    ids = []
    for number, title in enumerate(titles):
        clock["now"] = NOW + timedelta(minutes=number)
        ids.append(create(client, token, title).json()["id"])
    return ids


def test_el_listado_va_del_mas_nuevo_al_mas_viejo_y_pagina_con_cursor(
    client: TestClient, clock: dict[str, datetime], ana: str
) -> None:
    ids = create_many(client, clock, ana, ["a", "b", "c", "d", "e"])
    newest_first = list(reversed(ids))

    first = get(client, ana, "?limit=2").json()
    assert [item["id"] for item in first["items"]] == newest_first[:2]
    second = get(client, ana, f"?limit=2&cursor={first['next_cursor']}").json()
    assert [item["id"] for item in second["items"]] == newest_first[2:4]
    last = get(client, ana, f"?limit=2&cursor={second['next_cursor']}").json()
    assert [item["id"] for item in last["items"]] == newest_first[4:]
    assert last["next_cursor"] is None


def test_una_pagina_exacta_no_inventa_otra(
    client: TestClient, clock: dict[str, datetime], ana: str
) -> None:
    create_many(client, clock, ana, ["a", "b"])
    page = get(client, ana, "?limit=2").json()
    assert len(page["items"]) == 2
    assert page["next_cursor"] is None


def test_conceptos_creados_al_mismo_instante_no_se_pierden_entre_paginas(
    client: TestClient, ana: str
) -> None:
    ids = {create(client, ana, f"c{number}").json()["id"] for number in range(5)}  # misma hora
    seen: list[str] = []
    cursor = ""
    while True:
        page = get(client, ana, f"?limit=2{cursor}").json()
        seen += [item["id"] for item in page["items"]]
        if not page["next_cursor"]:
            break
        cursor = f"&cursor={page['next_cursor']}"
    assert len(seen) == 5
    assert set(seen) == ids


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "cursor=basura", "cursor=%25%25"])
def test_parametros_de_listado_invalidos(client: TestClient, ana: str, query: str) -> None:
    response = get(client, ana, f"?{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_buscar_ignora_mayusculas_y_trata_comodines_como_texto(
    client: TestClient, clock: dict[str, datetime], ana: str
) -> None:
    create_many(client, clock, ana, ["CI/CD", "Docker", "100% real", "a_b"])
    titles = lambda query: [item["title"] for item in get(client, ana, query).json()["items"]]  # noqa: E731
    assert titles("?q=ci") == ["CI/CD"]
    assert titles("?q=%25") == ["100% real"]
    assert titles("?q=_") == ["a_b"]
    assert titles("?q=%20") == titles("")  # solo espacios: sin filtro


def test_el_listado_muestra_el_titulo_de_la_ficha_cuando_la_hay(
    client: TestClient, ana: str, ai: FakeAIProvider
) -> None:
    ai.cards["ci"] = make_content("CI/CD (Integración continua)")
    create_and_process(client, ana, "ci")
    item = get(client, ana).json()["items"][0]
    assert item["title"] == "ci"
    assert item["card_title"] == "CI/CD (Integración continua)"
    assert item["status"] == "completed"
    assert "card" not in item  # el listado no carga la ficha entera


# --- Eliminar ---


def test_eliminar_borra_concepto_y_trabajo_pero_deja_la_ficha(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    concept_id = create_and_process(client, ana)
    response = client.delete(f"{BASE}/{concept_id}", headers=auth(ana))
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert (count(orm, "concepts"), count(orm, "processing_jobs")) == (0, 0)
    assert count(orm, "concept_cards") == 1
    assert get(client, ana, f"/{concept_id}").status_code == 404
    assert client.delete(f"{BASE}/{concept_id}", headers=auth(ana)).status_code == 404


def test_borrar_la_cuenta_borra_los_conceptos_y_deja_las_fichas(
    client: TestClient, orm: DbSession, ana: str, beto: str
) -> None:
    create_and_process(client, ana, "uno")
    mine_too = create_and_process(client, beto, "dos")
    from tests.helpers import PASSWORD

    response = client.request(
        "DELETE", "/api/v1/me", json={"password": PASSWORD}, headers=auth(ana)
    )
    assert response.status_code == 200
    assert count(orm, "concepts") == 1
    assert count(orm, "processing_jobs") == 1
    assert count(orm, "concept_cards") == 2
    assert get(client, beto, f"/{mine_too}").status_code == 200


# --- Aislamiento ---


def test_un_concepto_ajeno_responde_404_en_todos_los_endpoints(
    client: TestClient, orm: DbSession, ana: str, beto: str, ai: FakeAIProvider
) -> None:
    concept_id = create(client, ana, "privado").json()["id"]
    responses = [
        get(client, beto, f"/{concept_id}"),
        get(client, beto, f"/{concept_id}/status"),
        process(client, beto, concept_id),
        retry(client, beto, concept_id),
        client.delete(f"{BASE}/{concept_id}", headers=auth(beto)),
    ]
    assert [r.status_code for r in responses] == [404] * 5
    assert {r.json()["error"]["code"] for r in responses} == {"not_found"}
    # Y es idéntico a pedir uno que no existe.
    missing = get(client, beto, f"/{uuid.uuid4()}")
    assert missing.json() == responses[0].json()
    # Nada cambió para su dueña.
    assert ai.calls == []
    assert job_row(orm, concept_id).status == "pending"
    assert get(client, ana, f"/{concept_id}").status_code == 200


def test_cada_usuario_solo_ve_y_busca_en_lo_suyo(client: TestClient, ana: str, beto: str) -> None:
    create(client, ana, "secreto de ana")
    create(client, beto, "cosa de beto")
    assert [i["title"] for i in get(client, ana).json()["items"]] == ["secreto de ana"]
    assert [i["title"] for i in get(client, beto).json()["items"]] == ["cosa de beto"]
    assert get(client, beto, "?q=secreto").json()["items"] == []


def test_no_hay_forma_de_pasar_un_user_id(client: TestClient, ana: str, beto: str) -> None:
    other = create(client, beto, "de beto").json()["id"]
    assert get(client, ana, f"?user_id={other}").json()["items"] == []
    response = client.post(
        BASE, json={"title": "mio", "user_id": str(uuid.uuid4())}, headers=auth(ana)
    )
    assert response.status_code == 201
    assert len(get(client, ana).json()["items"]) == 1


# --- Registros ---


def test_los_registros_no_contienen_el_concepto(
    client: TestClient, caplog: pytest.LogCaptureFixture, ana: str, ai: FakeAIProvider
) -> None:
    caplog.set_level(logging.DEBUG)
    secret = "TituloMuySecreto-9137"
    create_and_process(client, ana, secret)
    ai.error = AIError("busy")
    failed = create(client, ana, secret + "-b").json()["id"]
    process(client, ana, failed)
    ai.error = RuntimeError(f"explotó con {secret}")
    unexpected = create(client, ana, secret + "-c").json()["id"]
    process(client, ana, unexpected)
    retry(client, ana, unexpected)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in logged
    assert "RuntimeError" in logged  # sí queda el tipo del fallo
