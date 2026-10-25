"""Repositorios de conceptos y fichas: aislamiento entre usuarios, búsqueda, paginación, cascada."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.models import Concept, ConceptAlias, ConceptCard, ProcessingJob, User, VideoCache
from app.repositories import (
    ConceptAliasRepository,
    ConceptCardRepository,
    ConceptRepository,
    NewVideo,
    VideoCacheRepository,
)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def add_user(orm: DbSession, email: str) -> User:
    user = User(email=email, password_hash="hash", language="es", timezone="UTC")
    orm.add(user)
    orm.flush()
    return user


@pytest.fixture
def two_users(orm: DbSession) -> tuple[User, User]:
    return add_user(orm, "ana@example.com"), add_user(orm, "beto@example.com")


def add_concept(
    orm: DbSession, user: User, title: str, minutes: int = 0, language: str = "es"
) -> Concept:
    return ConceptRepository(orm, user.id).create(
        title, language, "app", NOW + timedelta(minutes=minutes)
    )


def card_values(slug: str = "ci-cd", language: str = "es", **override: object) -> dict:
    values = {
        "canonical_title": "CI/CD",
        "cache_slug": slug,
        "language": language,
        "what_is": "Qué es",
        "what_for": "Para qué sirve",
        "example": "Un ejemplo",
        "example_code": None,
        "example_code_language": None,
        "model": "modelo-de-prueba",
        "now": NOW,
    }
    return {**values, **override}


def count(orm: DbSession, model: type) -> int:
    return orm.scalar(select(func.count()).select_from(model))


# --- Crear ---------------------------------------------------------------------------------


def test_crear_guarda_el_concepto_con_su_trabajo_pendiente(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    concept = add_concept(orm, ana, "CI/CD")
    assert concept.user_id == ana.id
    assert (concept.title, concept.language, concept.source) == ("CI/CD", "es", "app")
    assert concept.card_id is None
    job = concept.job
    assert (job.status, job.stage, job.attempts, job.max_attempts) == ("pending", "queued", 0, 3)
    assert job.user_id == ana.id
    assert job.next_run_at == NOW


@pytest.mark.parametrize("title", ["", "x" * 201])
def test_la_base_rechaza_titulos_vacios_o_demasiado_largos(
    orm: DbSession, two_users: tuple[User, User], title: str
) -> None:
    with pytest.raises(IntegrityError), orm.begin_nested():
        add_concept(orm, two_users[0], title)


def test_la_base_acepta_un_titulo_de_200_caracteres(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    assert add_concept(orm, two_users[0], "x" * 200).id


def test_la_base_rechaza_idioma_u_origen_desconocidos(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    with pytest.raises(IntegrityError), orm.begin_nested():
        add_concept(orm, ana, "CI/CD", language="fr")
    with pytest.raises(IntegrityError), orm.begin_nested():
        ConceptRepository(orm, ana.id).create("CI/CD", "es", "radio", NOW)


# --- Aislamiento ---------------------------------------------------------------------------


def test_un_concepto_ajeno_no_existe_para_otro_usuario(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    concept = add_concept(orm, ana, "CI/CD")
    assert ConceptRepository(orm, ana.id).get(concept.id) is not None
    assert ConceptRepository(orm, beto.id).get(concept.id) is None


def test_cada_usuario_solo_lista_sus_conceptos(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    add_concept(orm, ana, "de Ana")
    add_concept(orm, beto, "de Beto")
    assert [c.title for c in ConceptRepository(orm, ana.id).list_page(10)] == ["de Ana"]
    assert [c.title for c in ConceptRepository(orm, beto.id).list_page(10)] == ["de Beto"]


def test_la_busqueda_no_encuentra_conceptos_de_otro(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    add_concept(orm, ana, "Kubernetes")
    assert ConceptRepository(orm, beto.id).list_page(10, query="kube") == []


def test_no_se_puede_eliminar_el_concepto_de_otro(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    concept = add_concept(orm, ana, "CI/CD")
    assert ConceptRepository(orm, beto.id).delete(concept.id) is False
    assert ConceptRepository(orm, ana.id).get(concept.id) is not None


def test_un_concepto_que_no_existe_se_comporta_igual_que_uno_ajeno(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    repo = ConceptRepository(orm, two_users[0].id)
    assert repo.get(uuid.uuid4()) is None
    assert repo.delete(uuid.uuid4()) is False


# --- Listado, orden y paginación -----------------------------------------------------------


def test_lista_del_mas_nuevo_al_mas_viejo(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, _ = two_users
    add_concept(orm, ana, "primero", minutes=1)
    add_concept(orm, ana, "tercero", minutes=3)
    add_concept(orm, ana, "segundo", minutes=2)
    titles = [c.title for c in ConceptRepository(orm, ana.id).list_page(10)]
    assert titles == ["tercero", "segundo", "primero"]


def test_pagina_con_cursor_sin_repetir_ni_saltar(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    for number in range(5):
        add_concept(orm, ana, f"concepto {number}", minutes=number)
    repo = ConceptRepository(orm, ana.id)

    first = repo.list_page(2)
    second = repo.list_page(2, before=(first[-1].created_at, first[-1].id))
    third = repo.list_page(2, before=(second[-1].created_at, second[-1].id))
    assert [c.title for c in first + second + third] == [f"concepto {n}" for n in (4, 3, 2, 1, 0)]
    assert len(third) == 1


def test_con_la_misma_fecha_el_cursor_desempata_por_id(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    for number in range(3):
        add_concept(orm, ana, f"mismo instante {number}")  # las tres con la misma fecha
    repo = ConceptRepository(orm, ana.id)
    seen: list[uuid.UUID] = []
    before = None
    while page := repo.list_page(1, before=before):
        seen.append(page[0].id)
        before = (page[0].created_at, page[0].id)
    assert len(seen) == len(set(seen)) == 3


def test_la_lista_trae_la_ficha_y_el_estado(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, _ = two_users
    concept = add_concept(orm, ana, "CI/CD")
    card, _ = ConceptCardRepository(orm).insert_if_absent(**card_values())
    concept.card_id = card.id
    orm.flush()
    orm.expire_all()
    [item] = ConceptRepository(orm, ana.id).list_page(10)
    assert item.card.canonical_title == "CI/CD"
    assert item.job.status == "pending"


# --- Búsqueda ------------------------------------------------------------------------------


def test_la_busqueda_ignora_mayusculas_y_busca_dentro_del_titulo(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    add_concept(orm, ana, "Integración Continua")
    add_concept(orm, ana, "Docker")
    repo = ConceptRepository(orm, ana.id)
    assert [c.title for c in repo.list_page(10, query="continua")] == ["Integración Continua"]
    assert [c.title for c in repo.list_page(10, query="GRACIÓN")] == ["Integración Continua"]
    assert repo.list_page(10, query="zzz") == []


@pytest.mark.parametrize("special", ["%", "_", "\\", "100%", "a_b"])
def test_la_busqueda_trata_los_comodines_como_letras(
    orm: DbSession, two_users: tuple[User, User], special: str
) -> None:
    ana, _ = two_users
    add_concept(orm, ana, "normal")
    add_concept(orm, ana, "otro distinto")
    literal = add_concept(orm, ana, f"con {special} dentro")
    found = ConceptRepository(orm, ana.id).list_page(10, query=special)
    assert [c.id for c in found] == [literal.id]


def test_busqueda_vacia_devuelve_todo(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, _ = two_users
    add_concept(orm, ana, "uno")
    add_concept(orm, ana, "dos")
    assert len(ConceptRepository(orm, ana.id).list_page(10, query="")) == 2


# --- Eliminar y cascada --------------------------------------------------------------------


def test_eliminar_borra_el_concepto_y_su_trabajo_pero_no_la_ficha(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    concept = add_concept(orm, ana, "CI/CD")
    card, _ = ConceptCardRepository(orm).insert_if_absent(**card_values())
    concept.card_id = card.id
    orm.flush()

    assert ConceptRepository(orm, ana.id).delete(concept.id) is True
    orm.expire_all()
    assert ConceptRepository(orm, ana.id).get(concept.id) is None
    assert count(orm, ProcessingJob) == 0
    assert count(orm, ConceptCard) == 1


def test_eliminar_la_cuenta_borra_conceptos_y_trabajos_pero_conserva_las_fichas(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    mine = add_concept(orm, ana, "de Ana")
    add_concept(orm, beto, "de Beto")
    card, _ = ConceptCardRepository(orm).insert_if_absent(**card_values())
    mine.card_id = card.id
    orm.flush()

    orm.execute(delete(User).where(User.id == ana.id))
    orm.expire_all()
    assert [c.title for c in orm.scalars(select(Concept))] == ["de Beto"]
    assert count(orm, ProcessingJob) == 1
    assert count(orm, ConceptCard) == 1


def test_si_se_borra_la_ficha_el_concepto_se_queda_sin_ficha(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    concept = add_concept(orm, ana, "CI/CD")
    card, _ = ConceptCardRepository(orm).insert_if_absent(**card_values())
    concept.card_id = card.id
    orm.flush()

    orm.execute(delete(ConceptCard))  # lo que se haría por SQL con una ficha mala
    orm.expire_all()
    assert ConceptRepository(orm, ana.id).get(concept.id).card_id is None


# --- Fichas compartidas --------------------------------------------------------------------


def test_la_primera_ficha_gana_y_la_segunda_se_descarta(orm: DbSession) -> None:
    cards = ConceptCardRepository(orm)
    first, created_first = cards.insert_if_absent(**card_values(what_is="la primera"))
    second, created_second = cards.insert_if_absent(**card_values(what_is="la segunda"))
    assert (created_first, created_second) == (True, False)
    assert second.id == first.id
    assert second.what_is == "la primera"
    assert count(orm, ConceptCard) == 1


def test_el_mismo_slug_en_otro_idioma_es_otra_ficha(orm: DbSession) -> None:
    cards = ConceptCardRepository(orm)
    spanish, _ = cards.insert_if_absent(**card_values(language="es"))
    english, created = cards.insert_if_absent(**card_values(language="en"))
    assert created is True
    assert english.id != spanish.id


def test_busca_la_ficha_por_slug_e_idioma(orm: DbSession) -> None:
    cards = ConceptCardRepository(orm)
    card, _ = cards.insert_if_absent(**card_values())
    assert cards.get_by_slug("ci-cd", "es").id == card.id
    assert cards.get_by_slug("ci-cd", "en") is None
    assert cards.get_by_slug("docker", "es") is None


def test_la_ficha_guarda_el_codigo_de_ejemplo(orm: DbSession) -> None:
    card, _ = ConceptCardRepository(orm).insert_if_absent(
        **card_values(example_code="on: push", example_code_language="yaml")
    )
    assert (card.example_code, card.example_code_language) == ("on: push", "yaml")


def test_la_ficha_no_tiene_ninguna_columna_de_usuario() -> None:
    """Una ficha compartida no puede llevar datos de nadie (contexto.md §10.12)."""
    columns = set(ConceptCard.__table__.columns.keys())
    assert not columns & {"user_id", "title", "email", "concept_id"}


# --- Trabajos ------------------------------------------------------------------------------


def job_of(orm: DbSession, concept: Concept) -> ProcessingJob:
    orm.expire_all()
    return orm.scalar(select(ProcessingJob).where(ProcessingJob.concept_id == concept.id))


def test_reclamar_el_trabajo_lo_deja_en_processing_y_solo_una_vez(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    concept = add_concept(orm, ana, "Docker")
    repository = ConceptRepository(orm, ana.id)
    assert repository.claim_job(concept.id, NOW) is True
    job = job_of(orm, concept)
    assert (job.status, job.stage, job.locked_at) == ("processing", "writing", NOW)
    assert repository.claim_job(concept.id, NOW) is False  # ya no está pendiente


def test_un_usuario_no_puede_tocar_el_trabajo_de_otro(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    concept = add_concept(orm, ana, "Docker")
    other = ConceptRepository(orm, beto.id)
    assert other.claim_job(concept.id, NOW) is False
    other.fail_job(concept.id, "busy", NOW)
    assert job_of(orm, concept).status == "pending"
    other.complete_job(concept.id, NOW)
    assert job_of(orm, concept).status == "pending"
    # Para probar `reset_job` el trabajo tiene que estar en otro estado: lo toma su dueña.
    ConceptRepository(orm, ana.id).claim_job(concept.id, NOW)
    other.reset_job(concept.id, NOW)
    job = job_of(orm, concept)
    assert (job.status, job.attempts, job.last_error) == ("processing", 0, None)


def test_un_usuario_no_puede_poner_ficha_a_un_concepto_de_otro(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    concept = add_concept(orm, ana, "Docker")
    card, _ = ConceptCardRepository(orm).insert_if_absent(**card_values())
    ConceptRepository(orm, beto.id).attach_card(concept.id, card.id)
    orm.refresh(concept)
    assert concept.card_id is None
    ConceptRepository(orm, ana.id).attach_card(concept.id, card.id)
    orm.refresh(concept)
    assert concept.card_id == card.id


def test_fallar_suma_un_intento_y_guarda_solo_el_tipo_de_error(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    concept = add_concept(orm, ana, "Docker")
    repository = ConceptRepository(orm, ana.id)
    repository.claim_job(concept.id, NOW)
    repository.fail_job(concept.id, "busy", NOW)
    job = job_of(orm, concept)
    assert (job.status, job.attempts, job.last_error, job.locked_at) == ("failed", 1, "busy", None)
    repository.reset_job(concept.id, NOW)
    job = job_of(orm, concept)
    assert (job.status, job.stage, job.attempts, job.locked_at) == ("pending", "queued", 0, None)


# --- Alias ---------------------------------------------------------------------------------


def test_un_alias_lleva_a_su_ficha(orm: DbSession) -> None:
    card, _ = ConceptCardRepository(orm).insert_if_absent(**card_values())
    aliases = ConceptAliasRepository(orm)
    assert aliases.add_if_absent("es", "integracion continua", "ci-cd", NOW) is True
    found = aliases.get_card("es", "integracion continua")
    assert found is not None
    assert found.id == card.id


def test_un_alias_desconocido_no_lleva_a_ninguna_ficha(orm: DbSession) -> None:
    ConceptCardRepository(orm).insert_if_absent(**card_values())
    assert ConceptAliasRepository(orm).get_card("es", "algo nuevo") is None


def test_el_alias_solo_vale_en_su_idioma(orm: DbSession) -> None:
    ConceptCardRepository(orm).insert_if_absent(**card_values(language="es"))
    ConceptCardRepository(orm).insert_if_absent(**card_values(language="en"))
    aliases = ConceptAliasRepository(orm)
    aliases.add_if_absent("es", "docker", "ci-cd", NOW)
    assert aliases.get_card("en", "docker") is None


def test_el_primer_alias_gana_y_el_segundo_se_descarta(orm: DbSession) -> None:
    ConceptCardRepository(orm).insert_if_absent(**card_values(slug="ci-cd"))
    ConceptCardRepository(orm).insert_if_absent(**card_values(slug="otra"))
    aliases = ConceptAliasRepository(orm)
    assert aliases.add_if_absent("es", "ci cd", "ci-cd", NOW) is True
    assert aliases.add_if_absent("es", "ci cd", "otra", NOW) is False
    found = aliases.get_card("es", "ci cd")
    assert found is not None
    assert found.cache_slug == "ci-cd"
    assert orm.scalar(select(func.count()).select_from(ConceptAlias)) == 1


def test_la_ficha_guarda_la_consulta_de_youtube(orm: DbSession) -> None:
    card, _ = ConceptCardRepository(orm).insert_if_absent(
        **card_values(youtube_search_query="qué es CI/CD explicado")
    )
    assert card.youtube_search_query == "qué es CI/CD explicado"


def test_una_ficha_sin_consulta_de_youtube_queda_en_nulo(orm: DbSession) -> None:
    card, _ = ConceptCardRepository(orm).insert_if_absent(**card_values())
    assert card.youtube_search_query is None


# --- Videos --------------------------------------------------------------------------------


def video(number: int) -> NewVideo:
    return NewVideo(
        youtube_id=f"id{number}",
        title=f"Video {number}",
        channel=f"Canal {number}",
        thumbnail_url=f"https://i.ytimg.com/vi/id{number}/hqdefault.jpg",
    )


def test_los_videos_se_guardan_y_se_leen_en_orden(orm: DbSession) -> None:
    videos = VideoCacheRepository(orm)
    videos.save_if_absent("ci-cd", "es", [video(1), video(2)], NOW)
    found = videos.get("ci-cd", "es")
    assert [(v.position, v.youtube_id, v.title, v.channel) for v in found] == [
        (1, "id1", "Video 1", "Canal 1"),
        (2, "id2", "Video 2", "Canal 2"),
    ]


def test_sin_busqueda_previa_no_hay_videos(orm: DbSession) -> None:
    assert VideoCacheRepository(orm).get("ci-cd", "es") == []


def test_los_videos_son_por_concepto_e_idioma(orm: DbSession) -> None:
    videos = VideoCacheRepository(orm)
    videos.save_if_absent("ci-cd", "es", [video(1), video(2)], NOW)
    assert videos.get("ci-cd", "en") == []
    assert videos.get("docker", "es") == []


def test_solo_se_guardan_dos_videos(orm: DbSession) -> None:
    videos = VideoCacheRepository(orm)
    videos.save_if_absent("ci-cd", "es", [video(1), video(2), video(3)], NOW)
    assert [v.youtube_id for v in videos.get("ci-cd", "es")] == ["id1", "id2"]


def test_un_solo_video_tambien_vale(orm: DbSession) -> None:
    videos = VideoCacheRepository(orm)
    videos.save_if_absent("ci-cd", "es", [video(1)], NOW)
    assert [v.position for v in videos.get("ci-cd", "es")] == [1]


def test_sin_videos_no_se_guarda_nada(orm: DbSession) -> None:
    videos = VideoCacheRepository(orm)
    videos.save_if_absent("ci-cd", "es", [], NOW)
    assert videos.get("ci-cd", "es") == []
    assert orm.scalar(select(func.count()).select_from(VideoCache)) == 0


def test_la_primera_busqueda_gana_y_la_segunda_se_descarta(orm: DbSession) -> None:
    videos = VideoCacheRepository(orm)
    videos.save_if_absent("ci-cd", "es", [video(1), video(2)], NOW)
    videos.save_if_absent("ci-cd", "es", [video(8), video(9)], NOW)
    assert [v.youtube_id for v in videos.get("ci-cd", "es")] == ["id1", "id2"]


def test_el_titulo_de_un_video_se_guarda_tal_cual_como_texto(orm: DbSession) -> None:
    videos = VideoCacheRepository(orm)
    odd = NewVideo("abc", "<b>Hola</b> & 'adiós'", None, "https://i.ytimg.com/vi/abc/h.jpg")
    videos.save_if_absent("ci-cd", "es", [odd], NOW)
    saved = videos.get("ci-cd", "es")[0]
    assert (saved.title, saved.channel) == ("<b>Hola</b> & 'adiós'", None)
