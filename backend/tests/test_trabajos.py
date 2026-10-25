"""El trabajador de fichas y videos: alias, caché de videos, reintentos y el reloj (§4.3 y §4.4)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.main import app
from app.services import jobs
from app.services.ai import AIError
from app.services.youtube import Video, VideoError, get_video_provider
from tests.helpers import (
    HEADERS,
    NOW,
    FakeAIProvider,
    FakeEmailProvider,
    FakeVideoProvider,
    invite,
    make_content,
    register,
    signup,
    token_of,
    verify,
)

BASE = "/api/v1/concepts"
SECRET = "secreto-interno-de-prueba"
MINUTE = timedelta(minutes=1)


def auth(token: str) -> dict[str, str]:
    return {**HEADERS, "Cookie": f"cb_session={token}"}


def create(client: TestClient, token: str, title: str = "CI/CD") -> str:
    response = client.post(BASE, json={"title": title}, headers=auth(token))
    assert response.status_code == 201
    return response.json()["id"]


def process(client: TestClient, token: str, concept_id: str):
    return client.post(f"{BASE}/{concept_id}/process", headers=auth(token))


def create_and_process(client: TestClient, token: str, title: str = "CI/CD") -> str:
    concept_id = create(client, token, title)
    assert process(client, token, concept_id).status_code == 200
    return concept_id


def detail(client: TestClient, token: str, concept_id: str) -> dict:
    return client.get(f"{BASE}/{concept_id}", headers=auth(token)).json()


def count(orm: DbSession, table: str) -> int:
    return orm.execute(text(f"select count(*) from {table}")).scalar_one()


def job(orm: DbSession, concept_id: str):
    return orm.execute(
        text(
            "select status, stage, attempts, last_error, locked_at, next_run_at "
            "from processing_jobs where concept_id = :id"
        ),
        {"id": concept_id},
    ).one()


def set_job(orm: DbSession, concept_id: str, **columns: object) -> None:
    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    orm.execute(
        text(f"update processing_jobs set {assignments} where concept_id = :concept_id"),
        {**columns, "concept_id": concept_id},
    )
    orm.flush()


@pytest.fixture
def ana(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> str:
    return token_of(signup(client, orm, mailer))


@pytest.fixture
def beto(client: TestClient, orm: DbSession, mailer: FakeEmailProvider, ana: str) -> str:
    return token_of(signup(client, orm, mailer, email="beto@example.com"))


@pytest.fixture
def carol(client: TestClient, orm: DbSession, mailer: FakeEmailProvider, ana: str) -> str:
    """Una usuaria con la cuenta en inglés."""
    invite(orm, "carol@example.com")
    register(client, email="carol@example.com", language="en")
    return token_of(verify(client, mailer.last_code(), "carol@example.com"))


# --- Alias ---------------------------------------------------------------------------------


def test_un_texto_ya_visto_no_llama_a_gemini_y_usa_la_misma_ficha(
    client: TestClient, ana: str, beto: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    first = create_and_process(client, ana, "CI/CD")
    second = create_and_process(client, beto, "  ci/cd ")  # otra forma de escribir lo mismo
    assert len(ai.calls) == 1
    assert detail(client, ana, first)["card"] == detail(client, beto, second)["card"]
    assert detail(client, beto, second)["status"] == "completed"
    # Los videos tampoco se buscan otra vez.
    assert len(youtube.calls) == 1
    assert len(detail(client, beto, second)["videos"]) == 2


def test_el_alias_se_guarda_con_la_ficha_y_sin_datos_del_usuario(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    create_and_process(client, ana, "Integración  Continua")
    row = orm.execute(text("select language, alias, cache_slug from concept_aliases")).one()
    assert tuple(row) == ("es", "integracion continua", "integracion-continua")


def test_otra_forma_de_escribirlo_que_da_el_mismo_slug_gasta_gemini_una_vez(
    client: TestClient, orm: DbSession, ana: str, beto: str, ai: FakeAIProvider
) -> None:
    ai.cards["integración continua"] = make_content("CI/CD", cache_slug="ci-cd")
    create_and_process(client, ana, "CI/CD")
    create_and_process(client, ana, "integración continua")  # Gemini: otro texto, misma ficha
    assert len(ai.calls) == 2
    assert count(orm, "concept_cards") == 1
    assert count(orm, "concept_aliases") == 2
    # Desde entonces las dos formas se resuelven sin Gemini, también para otro usuario.
    create_and_process(client, beto, "Integración Continua")
    create_and_process(client, beto, "ci/cd")
    assert len(ai.calls) == 2


def test_un_titulo_de_mas_de_60_caracteres_no_crea_alias_pero_si_ficha(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    title = "concepto " * 8  # 72 caracteres, 71 al normalizar
    create_and_process(client, ana, title)
    assert count(orm, "concept_cards") == 1
    assert count(orm, "concept_aliases") == 0
    create_and_process(client, ana, title)  # sin alias, vuelve a Gemini; la ficha se comparte
    assert len(ai.calls) == 2
    assert count(orm, "concept_cards") == 1


def test_el_alias_vale_solo_en_su_idioma(
    client: TestClient, orm: DbSession, ana: str, carol: str, ai: FakeAIProvider
) -> None:
    create_and_process(client, ana, "Docker")
    create_and_process(client, carol, "docker")  # mismo texto, idioma inglés
    assert [language for _, language in ai.calls] == ["es", "en"]
    assert count(orm, "concept_cards") == 2


def test_acertar_con_un_alias_cuenta_para_el_limite_diario(
    client: TestClient, orm: DbSession, ana: str, beto: str
) -> None:
    create_and_process(client, ana, "CI/CD")
    create_and_process(client, beto, "ci/cd")
    used = orm.execute(
        text("select count(*) from rate_limit_events where bucket = 'concept_create'")
    ).scalar_one()
    assert used == 2  # el alias ahorra la IA, no el límite


def test_el_alias_solo_se_busca_si_el_concepto_aun_no_tiene_ficha(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create_and_process(client, ana, "CI/CD")
    # Como si el trabajo se hubiera quedado a medias con la ficha ya puesta.
    set_job(orm, concept_id, status="pending", stage="queued")
    assert process(client, ana, concept_id).json()["status"] == "completed"
    assert len(ai.calls) == 1


# --- Videos --------------------------------------------------------------------------------


def test_la_consulta_de_youtube_sale_de_la_ficha_y_va_en_el_idioma_del_concepto(
    client: TestClient, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    ai.cards["CI/CD"] = make_content("CI/CD", youtube_search_query="qué es CI/CD explicado")
    create_and_process(client, ana, "CI/CD")
    assert youtube.calls == [("qué es CI/CD explicado", "es")]


def test_sin_consulta_guardada_se_busca_con_el_titulo_de_la_ficha(
    client: TestClient, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    """Las fichas de la 6a no tienen consulta."""
    ai.cards["ci cd"] = make_content("CI/CD (Integración continua)", cache_slug="ci-cd")
    create_and_process(client, ana, "ci cd")
    assert youtube.calls == [("CI/CD (Integración continua)", "es")]


def test_dos_conceptos_con_la_misma_ficha_comparten_los_videos(
    client: TestClient, orm: DbSession, ana: str, beto: str, youtube: FakeVideoProvider
) -> None:
    first = create_and_process(client, ana, "CI/CD")
    second = create_and_process(client, beto, "ci cd")  # alias distinto, mismo slug
    assert len(youtube.calls) == 1
    assert detail(client, ana, first)["videos"] == detail(client, beto, second)["videos"]
    assert count(orm, "video_cache") == 2


def test_los_videos_son_por_idioma(
    client: TestClient, orm: DbSession, ana: str, carol: str, youtube: FakeVideoProvider
) -> None:
    create_and_process(client, ana, "Docker")
    create_and_process(client, carol, "Docker")
    assert [language for _, language in youtube.calls] == ["es", "en"]
    assert count(orm, "video_cache") == 4


@pytest.mark.parametrize(
    "error",
    [VideoError("quota"), VideoError("unavailable"), RuntimeError("algo raro")],
    ids=["cupo", "caido", "inesperado"],
)
def test_si_youtube_falla_la_ficha_se_entrega_sin_videos_y_no_es_un_fallo(
    client: TestClient,
    orm: DbSession,
    ana: str,
    youtube: FakeVideoProvider,
    error: Exception,
) -> None:
    youtube.error = error
    concept_id = create(client, ana)
    response = process(client, ana, concept_id)
    assert response.json() == {"status": "completed", "stage": "done", "attempts": 0}
    body = detail(client, ana, concept_id)
    assert body["card"]["what_is"] == "Qué es."
    assert body["videos"] == []
    assert job(orm, concept_id).last_error is None
    # El fallo no se recuerda: nada en la caché, y no se reintenta por su cuenta.
    assert count(orm, "video_cache") == 0
    assert len(youtube.calls) == 1


def test_el_siguiente_concepto_con_esa_ficha_vuelve_a_buscar_los_videos(
    client: TestClient, orm: DbSession, ana: str, beto: str, youtube: FakeVideoProvider
) -> None:
    youtube.error = VideoError("quota")
    create_and_process(client, ana, "CI/CD")
    youtube.error = None
    second = create_and_process(client, beto, "ci/cd")
    assert len(youtube.calls) == 2
    assert len(detail(client, beto, second)["videos"]) == 2


def test_sin_resultados_no_se_guarda_nada_en_la_cache(
    client: TestClient, orm: DbSession, ana: str, youtube: FakeVideoProvider
) -> None:
    youtube.videos = []
    concept_id = create_and_process(client, ana)
    assert detail(client, ana, concept_id)["videos"] == []
    assert count(orm, "video_cache") == 0


def test_un_fallo_de_la_base_al_guardar_videos_no_tira_la_ficha(
    client: TestClient, ana: str, youtube: FakeVideoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("base caída")

    monkeypatch.setattr(jobs.VideoCacheRepository, "save_if_absent", broken)
    concept_id = create(client, ana)
    assert process(client, ana, concept_id).json()["status"] == "completed"
    assert detail(client, ana, concept_id)["card"] is not None


def test_con_la_ficha_ya_puesta_solo_se_buscan_los_videos(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    youtube.error = VideoError("quota")
    concept_id = create_and_process(client, ana)
    youtube.error = None
    set_job(orm, concept_id, status="pending", stage="queued")
    assert process(client, ana, concept_id).json()["status"] == "completed"
    assert len(ai.calls) == 1
    assert len(detail(client, ana, concept_id)["videos"]) == 2


class SpyVideos:
    """Anota en qué etapa está el trabajo y si hay una transacción abierta durante la búsqueda."""

    def __init__(self, orm: DbSession, concept_id: Callable[[], str]) -> None:
        self.orm = orm
        self.concept_id = concept_id
        self.seen: dict[str, object] = {}

    def search(self, query: str, language: str) -> list[Video]:
        row = job(self.orm, self.concept_id())
        self.seen = {"in_transaction": self.orm.in_transaction(), "stage": row.stage}
        return []


def test_buscar_videos_es_una_etapa_y_no_mantiene_una_transaccion_abierta(
    client: TestClient, orm: DbSession, ana: str
) -> None:
    holder: list[str] = []
    spy = SpyVideos(orm, lambda: holder[0])
    app.dependency_overrides[get_video_provider] = lambda: spy
    concept_id = create(client, ana)
    holder.append(concept_id)
    process(client, ana, concept_id)
    # `job()` abre una transacción al leer, así que se comprueba solo lo que importa: la etapa.
    assert spy.seen["stage"] == "finding_videos"


def test_el_listado_no_trae_videos(client: TestClient, ana: str) -> None:
    create_and_process(client, ana)
    item = client.get(BASE, headers=auth(ana)).json()["items"][0]
    assert "videos" not in item


# --- Reintentos con espera -----------------------------------------------------------------


def test_un_fallo_pasivo_de_gemini_deja_el_trabajo_en_cola_con_espera(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider
) -> None:
    ai.error = AIError("busy")
    concept_id = create(client, ana)
    response = process(client, ana, concept_id)
    assert response.status_code == 200
    assert response.json() == {"status": "pending", "stage": "queued", "attempts": 1}
    row = job(orm, concept_id)
    assert (row.last_error, row.locked_at, row.next_run_at) == ("busy", None, NOW + 2 * MINUTE)
    assert count(orm, "concept_cards") == 0


def test_process_respeta_la_espera_y_no_llama_a_gemini_antes_de_tiempo(
    client: TestClient,
    clock: dict[str, datetime],
    ana: str,
    ai: FakeAIProvider,
) -> None:
    ai.error = AIError("busy")
    concept_id = create(client, ana)
    process(client, ana, concept_id)
    ai.error = None
    clock["now"] = NOW + MINUTE
    waiting = process(client, ana, concept_id)
    assert waiting.status_code == 202
    assert waiting.json() == {"status": "pending", "stage": "queued", "attempts": 1}
    assert len(ai.calls) == 1
    clock["now"] = NOW + 2 * MINUTE
    done = process(client, ana, concept_id)
    assert done.status_code == 200
    assert done.json() == {"status": "completed", "stage": "done", "attempts": 1}


def test_tres_intentos_en_total_con_esperas_de_2_y_4_minutos(
    client: TestClient,
    orm: DbSession,
    clock: dict[str, datetime],
    ana: str,
    ai: FakeAIProvider,
) -> None:
    ai.error = AIError("unavailable")
    concept_id = create(client, ana)
    process(client, ana, concept_id)
    assert job(orm, concept_id).next_run_at == NOW + 2 * MINUTE
    clock["now"] = NOW + 2 * MINUTE
    assert process(client, ana, concept_id).json()["attempts"] == 2
    assert job(orm, concept_id).next_run_at == NOW + 6 * MINUTE  # 4 minutos después del 2.º
    clock["now"] = NOW + 6 * MINUTE
    final = process(client, ana, concept_id)
    assert final.json() == {"status": "failed", "stage": "writing", "attempts": 3}
    assert job(orm, concept_id).last_error == "unavailable"
    assert len(ai.calls) == 3
    # Ya no hay más intentos solos: ni /process ni el reloj lo recogen.
    clock["now"] = NOW + 60 * MINUTE
    assert process(client, ana, concept_id).json()["status"] == "failed"
    assert len(ai.calls) == 3


@pytest.mark.parametrize("kind", ["rejected", "not_configured"])
def test_si_el_servicio_se_niega_no_se_reintenta(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, kind: str
) -> None:
    ai.error = AIError(kind)
    concept_id = create(client, ana)
    assert process(client, ana, concept_id).json()["status"] == "failed"
    assert job(orm, concept_id).attempts == 1


@pytest.mark.parametrize("kind", ["busy", "unavailable", "invalid_response"])
def test_los_fallos_pasajeros_se_reintentan(
    client: TestClient, ana: str, ai: FakeAIProvider, kind: str
) -> None:
    ai.error = AIError(kind)
    concept_id = create(client, ana)
    assert process(client, ana, concept_id).json()["status"] == "pending"


def test_tras_un_reintento_con_exito_consta_cuantos_intentos_fallaron(
    client: TestClient, clock: dict[str, datetime], ana: str, ai: FakeAIProvider
) -> None:
    ai.error = AIError("busy")
    concept_id = create(client, ana)
    process(client, ana, concept_id)
    ai.error = None
    clock["now"] = NOW + 2 * MINUTE
    process(client, ana, concept_id)
    status = client.get(f"{BASE}/{concept_id}/status", headers=auth(ana)).json()
    assert status == {"status": "completed", "stage": "done", "attempts": 1}


def test_el_intento_abandonado_cuenta_y_el_tercero_deja_el_trabajo_failed(
    client: TestClient,
    orm: DbSession,
    clock: dict[str, datetime],
    ana: str,
    ai: FakeAIProvider,
) -> None:
    concept_id = create(client, ana)
    set_job(orm, concept_id, status="processing", attempts=2, locked_at=NOW)
    clock["now"] = NOW + 6 * MINUTE
    response = process(client, ana, concept_id)
    assert response.json() == {"status": "failed", "stage": "queued", "attempts": 3}
    assert job(orm, concept_id).last_error == "abandoned"
    assert ai.calls == []


def test_un_trabajo_en_curso_de_otro_proceso_responde_202_sin_llamar_a_nadie(
    client: TestClient,
    orm: DbSession,
    clock: dict[str, datetime],
    ana: str,
    ai: FakeAIProvider,
    youtube: FakeVideoProvider,
) -> None:
    concept_id = create(client, ana)
    set_job(orm, concept_id, status="processing", stage="writing", locked_at=NOW)
    clock["now"] = NOW + 4 * MINUTE
    response = process(client, ana, concept_id)
    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    assert (ai.calls, youtube.calls) == ([], [])


# --- El reloj ------------------------------------------------------------------------------


def run_clock(orm: DbSession, ai, youtube, **kwargs: object) -> dict[str, int]:
    settings = {"max_jobs": 3, "budget_seconds": 30.0, **kwargs}
    counts = jobs.run_due_jobs(orm, ai, youtube, **settings)
    orm.commit()
    return counts


def test_el_reloj_procesa_los_trabajos_de_todos_los_usuarios(
    client: TestClient,
    orm: DbSession,
    ana: str,
    beto: str,
    ai: FakeAIProvider,
    youtube: FakeVideoProvider,
) -> None:
    first = create(client, ana, "Docker")
    second = create(client, beto, "Git")
    counts = run_clock(orm, ai, youtube)
    assert counts == {"due": 2, "completed": 2, "retrying": 0, "failed": 0, "skipped": 0}
    # Cada concepto lo ve su dueño, con su ficha y sus videos.
    assert detail(client, ana, first)["card"]["canonical_title"] == "Docker"
    assert detail(client, beto, second)["card"]["canonical_title"] == "Git"
    assert len(detail(client, ana, first)["videos"]) == 2


def test_el_reloj_no_trabaja_con_nada_si_no_hay_trabajos(
    orm: DbSession, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    counts = run_clock(orm, ai, youtube)
    assert counts == {"due": 0, "completed": 0, "retrying": 0, "failed": 0, "skipped": 0}
    assert (ai.calls, youtube.calls) == ([], [])


def test_el_reloj_procesa_como_mucho_max_jobs_por_llamada(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    ids = [create(client, ana, f"concepto {n}") for n in range(3)]
    assert run_clock(orm, ai, youtube, max_jobs=2)["completed"] == 2
    assert [job(orm, concept_id).status for concept_id in ids].count("pending") == 1
    assert run_clock(orm, ai, youtube, max_jobs=2)["completed"] == 1  # el resto, a la siguiente


def test_el_reloj_no_empieza_otro_trabajo_pasado_el_presupuesto_de_tiempo(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    ids = [create(client, ana, f"concepto {n}") for n in range(3)]
    times = iter([0.0, 31.0, 31.0])  # al empezar, y antes del 2.º y del 3.º
    counts = run_clock(orm, ai, youtube, monotonic=lambda: next(times))
    assert counts == {"due": 3, "completed": 1, "retrying": 0, "failed": 0, "skipped": 2}
    assert [job(orm, concept_id).status for concept_id in ids].count("completed") == 1


def test_el_reloj_siempre_hace_al_menos_un_trabajo(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    create(client, ana)
    counts = run_clock(orm, ai, youtube, budget_seconds=0.0)
    assert counts["completed"] == 1


def test_el_reloj_ignora_los_trabajos_a_los_que_aun_no_les_toca(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    concept_id = create(client, ana)
    set_job(orm, concept_id, next_run_at=NOW + MINUTE)
    assert run_clock(orm, ai, youtube, now=NOW)["due"] == 0
    assert ai.calls == []


def test_el_reloj_reintenta_lo_que_fallo_cuando_llega_su_hora(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    concept_id = create(client, ana)
    ai.error = AIError("busy")
    counts = run_clock(orm, ai, youtube, now=NOW)
    assert counts == {"due": 1, "completed": 0, "retrying": 1, "failed": 0, "skipped": 0}
    ai.error = None
    assert run_clock(orm, ai, youtube, now=NOW + MINUTE)["due"] == 0
    counts = run_clock(orm, ai, youtube, now=NOW + 2 * MINUTE)
    assert counts["completed"] == 1
    assert job(orm, concept_id).attempts == 1


def test_el_reloj_cuenta_los_trabajos_que_se_quedan_failed(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    create(client, ana)
    ai.error = AIError("rejected")
    counts = run_clock(orm, ai, youtube)
    assert (counts["completed"], counts["failed"]) == (0, 1)


def test_el_reloj_recoge_un_trabajo_abandonado_y_ese_intento_cuenta(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    concept_id = create(client, ana)
    set_job(orm, concept_id, status="processing", stage="writing", locked_at=NOW)
    assert run_clock(orm, ai, youtube, now=NOW + 4 * MINUTE)["due"] == 0  # sigue vigente
    counts = run_clock(orm, ai, youtube, now=NOW + 6 * MINUTE)
    assert counts["completed"] == 1
    assert job(orm, concept_id).attempts == 1


def test_un_trabajo_roto_en_el_reloj_no_para_a_los_demas(
    client: TestClient,
    orm: DbSession,
    ana: str,
    ai: FakeAIProvider,
    youtube: FakeVideoProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create(client, ana, "primero")
    create(client, ana, "segundo")
    real = jobs.run_job
    calls: list[int] = []

    def flaky(*args: object, **kwargs: object):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("base caída")
        return real(*args, **kwargs)

    monkeypatch.setattr(jobs, "run_job", flaky)
    counts = run_clock(orm, ai, youtube)
    assert (counts["completed"], counts["failed"]) == (1, 1)


def test_el_reloj_reparte_el_trabajo_con_el_mismo_codigo_que_process(
    client: TestClient, orm: DbSession, ana: str, ai: FakeAIProvider, youtube: FakeVideoProvider
) -> None:
    """Lo que deja el reloj es idéntico a lo que deja /process."""
    by_process = create_and_process(client, ana, "CI/CD")
    by_clock = create(client, ana, "Git")
    run_clock(orm, ai, youtube)
    a, b = detail(client, ana, by_process), detail(client, ana, by_clock)
    assert (a["status"], a["stage"], a["attempts"]) == (b["status"], b["stage"], b["attempts"])
    assert len(a["videos"]) == len(b["videos"]) == 2


# --- POST /internal/jobs -------------------------------------------------------------------


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "internal_secret", SECRET)


def call_jobs(client: TestClient, secret_value: str | None = SECRET):
    headers = {"X-Internal-Secret": secret_value} if secret_value else {}
    return client.post("/api/v1/internal/jobs", headers=headers)


def test_jobs_exige_el_secreto_interno(
    client: TestClient, secret: None, ai: FakeAIProvider
) -> None:
    assert call_jobs(client, None).status_code == 401
    assert call_jobs(client, "otro").status_code == 401
    assert ai.calls == []


def test_jobs_sin_secreto_configurado_responde_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "internal_secret", None)
    assert call_jobs(client).status_code == 503


def test_jobs_no_pide_la_cabecera_csrf_ni_una_sesion(
    client: TestClient, secret: None, ana: str, ai: FakeAIProvider
) -> None:
    concept_id = create(client, ana)
    client.cookies.clear()
    response = call_jobs(client)  # el reloj no manda cookie ni X-Requested-With
    assert response.status_code == 200
    assert response.json() == {"due": 1, "completed": 1, "retrying": 0, "failed": 0, "skipped": 0}
    assert len(ai.calls) == 1
    assert concept_id


def test_jobs_respeta_jobs_max_per_run(
    client: TestClient, secret: None, ana: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "jobs_max_per_run", 2)
    for number in range(3):
        create(client, ana, f"concepto {number}")
    assert call_jobs(client).json()["completed"] == 2
    assert call_jobs(client).json()["completed"] == 1


def test_jobs_solo_registra_numeros(
    client: TestClient,
    secret: None,
    ana: str,
    ai: FakeAIProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ai.error = AIError("busy")
    create(client, ana, "titulo-privado-123")
    with caplog.at_level(logging.DEBUG):
        call_jobs(client)
    assert "titulo-privado-123" not in caplog.text
    assert "jobs: {" in caplog.text
    assert "trabajo fallido: busy intento=1 reintento=True" in caplog.text


def test_el_acierto_de_las_caches_se_registra_como_contador_sin_texto(
    client: TestClient, ana: str, beto: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="compabook.jobs"):
        create_and_process(client, ana, "titulo-privado-123")
        create_and_process(client, beto, "titulo-privado-123")
    assert "trabajo terminado alias=miss videos=found" in caplog.text
    assert "trabajo terminado alias=hit videos=hit" in caplog.text
    assert "titulo-privado-123" not in caplog.text
    assert "Video 1" not in caplog.text
