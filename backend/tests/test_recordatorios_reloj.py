"""El reloj de recordatorios (§4.6): qué día y hora toca, a quién y sin duplicados."""

import logging
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.models import User
from app.repositories import (
    ConceptCardRepository,
    ConceptRepository,
    DueCandidate,
    PushSubscriptionRepository,
    ReminderRepository,
)
from app.services import reminders
from app.services.push import PushError, PushMessage, PushTarget
from tests.helpers import FakePushProvider

ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]
MONDAY = datetime(2026, 10, 26, tzinfo=UTC)  # lunes
SECRET = "secreto-interno-de-prueba"
ANA_DEVICE = "https://web.push.apple.com/wpush/v2/ana"
BETO_DEVICE = "https://fcm.googleapis.com/fcm/send/beto"


def at(hour: int, minute: int = 0, day: datetime = MONDAY) -> datetime:
    return day.replace(hour=hour, minute=minute)


def candidate(
    local_time: str = "20:00",
    weekdays: tuple[int, ...] = tuple(ALL_DAYS),
    timezone: str = "UTC",
    last_sent_on: date | None = None,
) -> DueCandidate:
    hour, minute = local_time.split(":")
    return DueCandidate(
        user_id=None,  # type: ignore[arg-type]
        timezone=timezone,
        language="es",
        local_time=time(int(hour), int(minute)),
        weekdays=weekdays,
        last_sent_on=last_sent_on,
    )


# --- Qué día y hora toca (función pura) -------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (at(19, 59), None),  # aún no
        (at(20, 0), date(2026, 10, 26)),  # justo a la hora
        (at(20, 1), date(2026, 10, 26)),
        (at(21, 59), date(2026, 10, 26)),  # último minuto de la ventana de 2 h
        (at(22, 0), None),  # ya pasó el margen
        (at(23, 30), None),
    ],
)
def test_toca_desde_la_hora_elegida_y_durante_dos_horas(
    now: datetime, expected: date | None
) -> None:
    found = reminders.reminder_day(candidate("20:00"), now)
    assert (found[0] if found else None) == expected


def test_devuelve_tambien_cuando_empezo_su_hora() -> None:
    found = reminders.reminder_day(candidate("20:00"), at(21, 15))
    assert found == (date(2026, 10, 26), at(20, 0))


@pytest.mark.parametrize(
    ("weekdays", "due"),
    [
        ((1,), True),  # el lunes toca
        ((2, 3, 4, 5, 6, 7), False),  # todos menos el lunes
        ((7,), False),
    ],
)
def test_solo_toca_los_dias_elegidos(weekdays: tuple[int, ...], due: bool) -> None:
    assert (reminders.reminder_day(candidate(weekdays=weekdays), at(20, 30)) is not None) == due


def test_el_domingo_es_el_dia_7() -> None:
    sunday = datetime(2026, 11, 1, tzinfo=UTC)
    assert reminders.reminder_day(candidate(weekdays=(7,)), at(20, 30, sunday)) is not None
    assert reminders.reminder_day(candidate(weekdays=(1,)), at(20, 30, sunday)) is None


def test_si_ya_se_envio_ese_dia_no_toca() -> None:
    assert reminders.reminder_day(candidate(last_sent_on=date(2026, 10, 26)), at(20, 30)) is None


def test_un_envio_de_otro_dia_no_impide_el_de_hoy() -> None:
    for sent in (date(2026, 10, 25), date(2026, 10, 19), None):
        assert reminders.reminder_day(candidate(last_sent_on=sent), at(20, 30)) is not None


def test_la_hora_es_la_del_usuario_no_la_utc() -> None:
    # 20:00 en Santo Domingo (UTC-4, sin cambio de hora) son las 00:00 UTC del día siguiente.
    santo_domingo = candidate("20:00", timezone="America/Santo_Domingo")
    assert reminders.reminder_day(santo_domingo, at(20, 30)) is None  # 16:30 allí
    found = reminders.reminder_day(santo_domingo, at(0, 30, MONDAY + timedelta(days=1)))
    assert found is not None and found[0] == date(2026, 10, 26)  # su lunes, no el martes UTC


def test_el_dia_de_la_semana_es_el_local_no_el_utc() -> None:
    martes_utc = at(0, 30, MONDAY + timedelta(days=1))  # lunes 20:30 en Santo Domingo
    santo_domingo = candidate("20:00", weekdays=(1,), timezone="America/Santo_Domingo")
    assert reminders.reminder_day(santo_domingo, martes_utc) is not None
    solo_martes = candidate("20:00", weekdays=(2,), timezone="America/Santo_Domingo")
    assert reminders.reminder_day(solo_martes, martes_utc) is None


def test_una_zona_al_otro_lado_del_mundo() -> None:
    # 07:30 en Auckland (UTC+13 en octubre) es las 18:30 UTC del día anterior.
    auckland = candidate("07:30", timezone="Pacific/Auckland")
    found = reminders.reminder_day(auckland, at(18, 45, MONDAY - timedelta(days=1)))
    assert found is not None and found[0] == date(2026, 10, 26)


def test_la_ventana_que_cruza_la_medianoche_pertenece_al_dia_anterior() -> None:
    now = at(0, 30, MONDAY + timedelta(days=1))  # martes 00:30; el aviso de las 23:30 era del lunes
    found = reminders.reminder_day(candidate("23:30", weekdays=(1,)), now)
    assert found is not None and found[0] == date(2026, 10, 26)
    assert (
        reminders.reminder_day(candidate("23:30", weekdays=(2,)), now) is None
    )  # no es del martes
    assert (
        reminders.reminder_day(
            candidate("23:30", weekdays=(1,)), at(1, 30, MONDAY + timedelta(days=1))
        )
        is None
    )


def test_pasada_la_medianoche_no_se_repite_el_aviso_ya_enviado() -> None:
    now = at(0, 30, MONDAY + timedelta(days=1))
    sent = date(2026, 10, 26)  # se mandó el lunes a las 23:30
    assert reminders.reminder_day(candidate("23:30", last_sent_on=sent), now) is None


def test_una_zona_desconocida_se_ignora_sin_romper() -> None:
    assert reminders.reminder_day(candidate(timezone="Marte/Olympus"), at(20, 30)) is None


# Cambio de hora (Madrid): el 29/03/2026 los relojes saltan de las 02:00 a las 03:00 y el
# 25/10/2026 vuelven de las 03:00 a las 02:00.


def test_cambio_de_hora_de_primavera_la_hora_que_no_existe_cuenta_desde_su_equivalente() -> None:
    madrid = candidate("02:30", timezone="Europe/Madrid")
    day = datetime(2026, 3, 29, tzinfo=UTC)
    assert reminders.reminder_day(madrid, at(1, 29, day)) is None
    found = reminders.reminder_day(madrid, at(1, 30, day))  # 01:30 UTC = 03:30 en Madrid ese día
    assert found is not None and found[0] == date(2026, 3, 29)
    assert reminders.reminder_day(madrid, at(3, 29, day)) is not None
    assert reminders.reminder_day(madrid, at(3, 30, day)) is None


def test_cambio_de_hora_de_otono_la_hora_repetida_cuenta_desde_la_primera() -> None:
    madrid = candidate("02:30", timezone="Europe/Madrid")
    day = datetime(2026, 10, 25, tzinfo=UTC)
    assert reminders.reminder_day(madrid, at(0, 29, day)) is None
    assert reminders.reminder_day(madrid, at(0, 30, day)) is not None  # 02:30 CEST
    assert reminders.reminder_day(madrid, at(1, 45, day)) is not None  # 02:45 CET, aún en ventana
    assert reminders.reminder_day(madrid, at(2, 30, day)) is None


def test_un_dia_de_cambio_de_hora_solo_toca_una_vez() -> None:
    madrid = candidate("02:30", timezone="Europe/Madrid")
    day = datetime(2026, 10, 25, tzinfo=UTC)
    due_minutes = 0
    for minute in range(0, 24 * 60):
        now = day + timedelta(minutes=minute)
        if reminders.reminder_day(madrid, now) is not None:
            due_minutes += 1
    assert due_minutes == 120  # una sola ventana de 2 h


# --- El mensaje -------------------------------------------------------------------------------


def test_mensaje_en_espanol_y_en_ingles_con_singular() -> None:
    es = reminders.reminder_message("es", 12, "CI/CD", "abc")
    assert es.body == 'Tienes 12 conceptos en tu Cuaderno — repasa "CI/CD"'
    assert reminders.reminder_message("es", 1, "CI/CD", "abc").body == (
        'Tienes 1 concepto en tu Cuaderno — repasa "CI/CD"'
    )
    en = reminders.reminder_message("en", 12, "CI/CD", "abc")
    assert en.body == 'You have 12 concepts in your Notebook — review "CI/CD"'
    assert reminders.reminder_message("en", 1, "CI/CD", "abc").body == (
        'You have 1 concept in your Notebook — review "CI/CD"'
    )
    assert (es.title, es.url, es.tag, es.ttl) == ("CompaBook", "/cuaderno/abc", "reminder", 3600)


def test_un_idioma_desconocido_usa_espanol() -> None:
    assert reminders.reminder_message("fr", 3, "CI/CD", "abc").body.startswith("Tienes 3")


def test_un_titulo_largo_se_recorta() -> None:
    title = "x" * 200
    body = reminders.reminder_message("es", 3, title, "abc").body
    assert "x" * 79 + "…" in body and "x" * 80 not in body
    assert reminders.reminder_message("es", 3, "x" * 80, "abc").body.count("x") == 80


# --- El reloj con la base de datos ------------------------------------------------------------


def add_user(
    orm: DbSession,
    email: str,
    timezone: str = "UTC",
    language: str = "es",
    disabled: bool = False,
) -> User:
    user = User(
        email=email,
        password_hash="hash",
        language=language,
        timezone=timezone,
        disabled_at=MONDAY if disabled else None,
    )
    orm.add(user)
    orm.flush()
    return user


def set_reminders(
    orm: DbSession,
    user: User,
    local_time: str = "20:00",
    weekdays: list[int] | None = None,
    enabled: bool = True,
) -> None:
    ReminderRepository(orm, user.id).save(
        enabled, reminders.parse_local_time(local_time), weekdays or ALL_DAYS, MONDAY
    )


def add_device(orm: DbSession, user: User, endpoint: str, active: bool = True) -> None:
    repository = PushSubscriptionRepository(orm, user.id)
    repository.upsert(endpoint, "clave", "secreto", None, MONDAY)
    if not active:
        repository.deactivate(endpoint)


_cards = {"n": 0}


def add_concept(orm: DbSession, user: User, title: str, done: bool = True):
    _cards["n"] += 1
    concepts = ConceptRepository(orm, user.id)
    concept = concepts.create(title, "es", "app", MONDAY)
    if done:
        card, _ = ConceptCardRepository(orm).insert_if_absent(
            canonical_title=f"Ficha de {title}",
            cache_slug=f"ficha-{_cards['n']}",
            language="es",
            what_is="a",
            what_for="b",
            example="c",
            example_code=None,
            example_code_language=None,
            model="modelo",
            now=MONDAY,
        )
        concepts.attach_card(concept.id, card.id)
        concepts.complete_job(concept.id, MONDAY)
    orm.flush()
    return concept


def last_sent(orm: DbSession, user: User) -> date | None:
    settings = ReminderRepository(orm, user.id).get()
    return settings.last_sent_on if settings else None


def run(orm: DbSession, push: FakePushProvider, now: datetime, **kwargs: object) -> dict[str, int]:
    options = {"max_users": 30, "budget_seconds": 25.0, **kwargs}
    return reminders.run_due_reminders(orm, push, now=now, **options)  # type: ignore[arg-type]


@pytest.fixture
def ana(orm: DbSession) -> User:
    """Ana: recordatorio a las 20:00 todos los días, un dispositivo y dos conceptos terminados."""
    user = add_user(orm, "ana@example.com")
    set_reminders(orm, user)
    add_device(orm, user, ANA_DEVICE)
    add_concept(orm, user, "Docker")
    add_concept(orm, user, "Git")
    return user


def sent_to(push: FakePushProvider, endpoint: str) -> list[PushMessage]:
    return [message for target, message in push.sent if target.endpoint == endpoint]


def test_avisa_a_quien_le_toca_con_uno_de_sus_conceptos(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    counts = run(orm, push, at(20, 5))
    assert counts == {"checked": 1, "due": 1, "sent": 1, "retrying": 0, "failed": 0, "skipped": 0}
    ((target, message),) = push.sent
    assert target == PushTarget(ANA_DEVICE, "clave", "secreto")
    assert message.body in (
        'Tienes 2 conceptos en tu Cuaderno — repasa "Ficha de Docker"',
        'Tienes 2 conceptos en tu Cuaderno — repasa "Ficha de Git"',
    )
    concept_id = message.url.removeprefix("/cuaderno/")
    owned = {str(c.id) for c in ConceptRepository(orm, ana.id).list_page(10)}
    assert concept_id in owned
    assert (message.tag, message.ttl) == ("reminder", 3600)
    assert last_sent(orm, ana) == date(2026, 10, 26)


def test_el_aviso_abre_el_concepto_que_nombra(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    run(orm, push, at(20, 5))
    message = push.sent[0][1]
    concept = ConceptRepository(orm, ana.id).get(uuid.UUID(message.url.removeprefix("/cuaderno/")))
    assert concept is not None and concept.card is not None
    assert f'"{concept.card.canonical_title}"' in message.body


def test_a_cualquier_hora_fuera_de_la_ventana_no_avisa(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    for now in (at(19, 59), at(22, 0), at(3, 0), at(12, 0)):
        counts = run(orm, push, now)
        assert (counts["sent"], counts["due"]) == (0, 0)
    assert push.sent == []
    assert last_sent(orm, ana) is None


def test_si_la_ejecucion_se_retrasa_la_siguiente_avisa_igual(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    # No hubo ejecuciones a las 20:00; a las 21:40 todavía está dentro de las 2 h.
    assert run(orm, push, at(21, 40))["sent"] == 1


def test_no_avisa_el_mismo_dia_dos_veces(orm: DbSession, push: FakePushProvider, ana: User) -> None:
    run(orm, push, at(20, 0))
    for minute in range(1, 110):
        assert run(orm, push, at(20, 0) + timedelta(minutes=minute))["sent"] == 0
    assert len(push.sent) == 1


def test_al_dia_siguiente_vuelve_a_avisar(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    run(orm, push, at(20, 0))
    assert run(orm, push, at(20, 0, MONDAY + timedelta(days=1)))["sent"] == 1
    assert len(push.sent) == 2


def test_cambiar_la_hora_el_mismo_dia_no_repite_el_aviso(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    run(orm, push, at(20, 0))
    set_reminders(orm, ana, "21:00")
    assert run(orm, push, at(21, 5))["sent"] == 0


def test_los_dias_no_elegidos_no_avisan(orm: DbSession, push: FakePushProvider, ana: User) -> None:
    set_reminders(orm, ana, weekdays=[2, 3, 4, 5, 6, 7])  # todos menos el lunes
    assert run(orm, push, at(20, 30))["due"] == 0
    assert push.sent == []


def test_un_recordatorio_apagado_no_avisa(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    set_reminders(orm, ana, enabled=False)
    counts = run(orm, push, at(20, 30))
    assert (counts["checked"], counts["sent"]) == (0, 0)


def test_sin_dispositivos_activos_no_avisa(orm: DbSession, push: FakePushProvider) -> None:
    user = add_user(orm, "sin@example.com")
    set_reminders(orm, user)
    add_concept(orm, user, "Docker")
    add_device(orm, user, ANA_DEVICE, active=False)
    counts = run(orm, push, at(20, 30))
    assert (counts["checked"], counts["sent"]) == (0, 0)


def test_una_cuenta_suspendida_no_recibe_avisos(orm: DbSession, push: FakePushProvider) -> None:
    user = add_user(orm, "suspendida@example.com", disabled=True)
    set_reminders(orm, user)
    add_device(orm, user, ANA_DEVICE)
    add_concept(orm, user, "Docker")
    assert run(orm, push, at(20, 30))["checked"] == 0


def test_con_el_cuaderno_vacio_no_se_envia_nada_y_se_puede_avisar_mas_tarde(
    orm: DbSession, push: FakePushProvider
) -> None:
    user = add_user(orm, "vacio@example.com")
    set_reminders(orm, user)
    add_device(orm, user, ANA_DEVICE)
    counts = run(orm, push, at(20, 0))
    assert (counts["due"], counts["sent"], counts["skipped"]) == (1, 0, 1)
    assert push.sent == [] and last_sent(orm, user) is None
    add_concept(orm, user, "Docker")  # añade uno dentro de la ventana: ahora sí
    assert run(orm, push, at(20, 30))["sent"] == 1


def test_solo_cuentan_los_conceptos_con_la_ficha_terminada(
    orm: DbSession, push: FakePushProvider
) -> None:
    user = add_user(orm, "mezcla@example.com")
    set_reminders(orm, user)
    add_device(orm, user, ANA_DEVICE)
    add_concept(orm, user, "Pendiente", done=False)
    add_concept(orm, user, "Pendiente 2", done=False)
    add_concept(orm, user, "Terminado")
    run(orm, push, at(20, 0))
    assert push.sent[0][1].body == 'Tienes 1 concepto en tu Cuaderno — repasa "Ficha de Terminado"'


def test_un_concepto_con_ficha_pero_aun_buscando_videos_no_cuenta(
    orm: DbSession, push: FakePushProvider
) -> None:
    user = add_user(orm, "videos@example.com")
    set_reminders(orm, user)
    add_device(orm, user, ANA_DEVICE)
    en_curso = add_concept(orm, user, "En curso")  # ya tiene ficha...
    orm.execute(
        text(
            "update processing_jobs set status = 'processing', stage = 'finding_videos' "
            "where concept_id = :id"
        ),
        {"id": en_curso.id},
    )  # ...pero aún busca los videos: abrirlo enseñaría el panel de carga
    add_concept(orm, user, "Listo")
    run(orm, push, at(20, 0))
    assert push.sent[0][1].body == 'Tienes 1 concepto en tu Cuaderno — repasa "Ficha de Listo"'


def test_con_solo_conceptos_pendientes_es_como_el_cuaderno_vacio(
    orm: DbSession, push: FakePushProvider
) -> None:
    user = add_user(orm, "pendiente@example.com")
    set_reminders(orm, user)
    add_device(orm, user, ANA_DEVICE)
    add_concept(orm, user, "Pendiente", done=False)
    assert run(orm, push, at(20, 0))["sent"] == 0


def test_el_aviso_nombra_conceptos_de_su_dueno_y_en_su_idioma(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    beto = add_user(orm, "beto@example.com", language="en")
    set_reminders(orm, beto)
    add_device(orm, beto, BETO_DEVICE)
    add_concept(orm, beto, "Kubernetes")
    counts = run(orm, push, at(20, 5))
    assert counts["sent"] == 2
    assert sent_to(push, BETO_DEVICE)[0].body == (
        'You have 1 concept in your Notebook — review "Ficha de Kubernetes"'
    )
    for message in sent_to(push, ANA_DEVICE):
        assert "Kubernetes" not in message.body and message.body.startswith("Tienes 2")


def test_cada_usuario_con_su_zona_horaria(orm: DbSession, push: FakePushProvider) -> None:
    santo_domingo = add_user(orm, "sd@example.com", timezone="America/Santo_Domingo")
    madrid = add_user(orm, "madrid@example.com", timezone="Europe/Madrid")
    for user, endpoint in ((santo_domingo, ANA_DEVICE), (madrid, BETO_DEVICE)):
        set_reminders(orm, user, "20:00")
        add_device(orm, user, endpoint)
        add_concept(orm, user, "Docker")
    # A las 19:15 UTC, en Madrid (UTC+1 desde el 25 de octubre) son las 20:15 y en Santo Domingo
    # (UTC-4), las 15:15.
    counts = run(orm, push, at(19, 15))
    assert counts["sent"] == 1
    assert [t.endpoint for t, _ in push.sent] == [BETO_DEVICE]
    # A las 00:15 UTC del martes son las 20:15 del lunes en Santo Domingo.
    counts = run(orm, push, at(0, 15, MONDAY + timedelta(days=1)))
    assert [t.endpoint for t, _ in push.sent] == [BETO_DEVICE, ANA_DEVICE]
    assert last_sent(orm, santo_domingo) == date(2026, 10, 26)


def test_se_envia_a_todos_los_dispositivos_del_usuario(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    add_device(orm, ana, GOOGLE := "https://fcm.googleapis.com/fcm/send/ana-android")
    run(orm, push, at(20, 5))
    assert {t.endpoint for t, _ in push.sent} == {ANA_DEVICE, GOOGLE}
    assert push.sent[0][1] == push.sent[1][1]  # el mismo aviso en los dos


def test_un_dispositivo_caducado_se_da_de_baja_y_el_otro_recibe(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    add_device(orm, ana, GOOGLE := "https://fcm.googleapis.com/fcm/send/ana-android")
    push.errors[GOOGLE] = PushError("expired")
    counts = run(orm, push, at(20, 5))
    assert (counts["sent"], counts["retrying"], counts["failed"]) == (1, 0, 0)
    assert [d.endpoint for d in PushSubscriptionRepository(orm, ana.id).list_active()] == [
        ANA_DEVICE
    ]
    assert last_sent(orm, ana) == date(2026, 10, 26)


def test_si_nadie_lo_recibe_por_un_fallo_pasajero_se_reintenta_el_minuto_siguiente(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    push.error = PushError("unavailable")
    counts = run(orm, push, at(20, 0))
    assert (counts["sent"], counts["retrying"], counts["failed"]) == (0, 1, 0)
    assert last_sent(orm, ana) is None  # el reclamo se devolvió
    assert len(PushSubscriptionRepository(orm, ana.id).list_active()) == 1  # sigue suscrito
    push.error = None
    assert run(orm, push, at(20, 1))["sent"] == 1
    assert last_sent(orm, ana) == date(2026, 10, 26)


def test_un_rechazo_tambien_se_reintenta_pero_solo_dentro_de_la_ventana(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    push.error = PushError("rejected")
    assert run(orm, push, at(20, 0))["retrying"] == 1
    assert run(orm, push, at(21, 59))["retrying"] == 1
    assert run(orm, push, at(22, 0))["due"] == 0  # fuera de la ventana: se acabó
    assert push.sent == []


def test_al_liberar_el_reclamo_se_conserva_el_envio_anterior(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    run(orm, push, at(20, 0, MONDAY - timedelta(days=1)))  # domingo
    assert last_sent(orm, ana) == date(2026, 10, 25)
    push.error = PushError("unavailable")
    run(orm, push, at(20, 0))
    assert last_sent(orm, ana) == date(2026, 10, 25)


def test_sin_claves_vapid_no_se_reintenta_cada_minuto(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    push.error = PushError("not_configured")
    assert run(orm, push, at(20, 0))["failed"] == 1
    assert run(orm, push, at(20, 1))["due"] == 0  # el día quedó reclamado


def test_si_todos_los_dispositivos_caducaron_se_dan_de_baja_y_no_se_insiste(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    push.error = PushError("expired")
    counts = run(orm, push, at(20, 0))
    assert (counts["failed"], counts["retrying"]) == (1, 0)
    assert PushSubscriptionRepository(orm, ana.id).list_active() == []
    assert run(orm, push, at(20, 1))["checked"] == 0  # ya no tiene dispositivos activos


def test_un_fallo_inesperado_con_un_usuario_no_para_a_los_demas(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    class Broken(FakePushProvider):
        def send(self, target: PushTarget, message: PushMessage) -> None:
            if target.endpoint == ANA_DEVICE:
                raise RuntimeError("algo raro")
            super().send(target, message)

    broken = Broken()
    beto = add_user(orm, "beto@example.com")
    set_reminders(orm, beto)
    add_device(orm, beto, BETO_DEVICE)
    add_concept(orm, beto, "Kubernetes")
    counts = run(orm, broken, at(20, 5))
    assert (counts["failed"], counts["sent"]) == (1, 1)
    assert [t.endpoint for t, _ in broken.sent] == [BETO_DEVICE]


def test_dos_ejecuciones_a_la_vez_no_duplican_el_aviso(orm: DbSession, ana: User) -> None:
    """Mientras la primera espera al servicio de push, llega otra ejecución del reloj."""

    class Reentrant(FakePushProvider):
        inner: dict[str, int] | None = None

        def send(self, target: PushTarget, message: PushMessage) -> None:
            if self.inner is None:
                self.inner = run(orm, self, at(20, 1))
            super().send(target, message)

    push = Reentrant()
    outer = run(orm, push, at(20, 0))
    assert outer["sent"] == 1
    assert push.inner is not None and push.inner["sent"] == 0 and push.inner["due"] == 0
    assert len(push.sent) == 1


def test_quien_pierde_la_carrera_por_el_envio_no_manda_nada(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    # Otra ejecución ya se quedó con el envío después de que esta lo viera pendiente.
    assert ReminderRepository(orm, ana.id).claim_send(date(2026, 10, 26))
    found = reminders.reminder_day(
        candidate("20:00", last_sent_on=None), at(20, 5)
    )  # esta ejecución leyó la lista antes
    assert found is not None
    mine = replace(candidate("20:00"), user_id=ana.id)
    outcome = reminders._remind(orm, push, mine, found[0])
    assert outcome == "skipped" and push.sent == []


def test_a_quien_lleva_mas_tiempo_esperando_se_le_avisa_primero(
    orm: DbSession, push: FakePushProvider
) -> None:
    for email, local_time, endpoint in (
        ("tarde@example.com", "20:30", ANA_DEVICE),
        ("pronto@example.com", "20:00", BETO_DEVICE),
    ):
        user = add_user(orm, email)
        set_reminders(orm, user, local_time)
        add_device(orm, user, endpoint)
        add_concept(orm, user, "Docker")
    run(orm, push, at(21, 0))
    assert [t.endpoint for t, _ in push.sent] == [BETO_DEVICE, ANA_DEVICE]


def test_hay_un_maximo_de_usuarios_por_ejecucion_y_el_resto_queda_para_la_siguiente(
    orm: DbSession, push: FakePushProvider
) -> None:
    users = []
    for n in range(4):
        user = add_user(orm, f"u{n}@example.com")
        set_reminders(orm, user)
        add_device(orm, user, f"https://web.push.apple.com/wpush/v2/{n}")
        add_concept(orm, user, "Docker")
        users.append(user)
    counts = run(orm, push, at(20, 0), max_users=3)
    assert (counts["due"], counts["sent"], counts["skipped"]) == (4, 3, 1)
    assert run(orm, push, at(20, 1), max_users=3)["sent"] == 1  # la que quedó
    assert len(push.sent) == 4


def test_si_se_agota_el_presupuesto_de_tiempo_no_empieza_con_otro(
    orm: DbSession, push: FakePushProvider
) -> None:
    for n in range(3):
        user = add_user(orm, f"u{n}@example.com")
        set_reminders(orm, user)
        add_device(orm, user, f"https://web.push.apple.com/wpush/v2/{n}")
        add_concept(orm, user, "Docker")
    ticks = iter([0.0, 26.0, 27.0])  # al llegar al segundo ya pasaron 26 s de los 25
    counts = run(orm, push, at(20, 0), monotonic=lambda: next(ticks))
    assert (counts["sent"], counts["skipped"]) == (1, 2)


def test_siempre_atiende_al_menos_a_uno_aunque_el_presupuesto_sea_cero(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    assert run(orm, push, at(20, 0), budget_seconds=0.0)["sent"] == 1


def test_los_registros_solo_llevan_contadores(
    orm: DbSession, push: FakePushProvider, ana: User, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    run(orm, push, at(20, 0))
    ana_2 = add_user(orm, "beto@example.com")
    set_reminders(orm, ana_2)
    add_device(orm, ana_2, BETO_DEVICE)
    add_concept(orm, ana_2, "Kubernetes")
    push.error = PushError("unavailable")
    run(orm, push, at(20, 1))
    logs = caplog.text
    assert "recordatorio sent" in logs and "recordatorio retrying" in logs
    for secret in ("Docker", "Git", "Kubernetes", "ana@example.com", ANA_DEVICE, BETO_DEVICE):
        assert secret not in logs
    assert "clave" not in logs and "secreto" not in logs


# --- POST /internal/reminders -----------------------------------------------------------------


@pytest.fixture
def internal(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "internal_secret", SECRET)

    def call(secret_value: str | None = SECRET):
        headers = {"X-Internal-Secret": secret_value} if secret_value else {}
        return client.post("/api/v1/internal/reminders", headers=headers)

    return call


def test_el_endpoint_exige_el_secreto(internal, push: FakePushProvider, ana: User) -> None:
    assert internal(None).status_code == 401
    assert internal("otro").status_code == 401
    assert push.sent == []


def test_sin_secreto_configurado_el_endpoint_responde_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "internal_secret", None)
    response = client.post("/api/v1/internal/reminders", headers={"X-Internal-Secret": SECRET})
    assert response.status_code == 503


def test_el_endpoint_avisa_y_responde_solo_contadores(
    internal, clock: dict[str, datetime], push: FakePushProvider, ana: User
) -> None:
    clock["now"] = at(20, 10)
    response = internal()  # sin cabecera CSRF: lo llama pg_cron, no un navegador
    assert response.status_code == 200
    assert response.json() == {
        "checked": 1,
        "due": 1,
        "sent": 1,
        "retrying": 0,
        "failed": 0,
        "skipped": 0,
    }
    assert len(push.sent) == 1
    clock["now"] = at(20, 11)
    assert internal().json()["sent"] == 0


def test_el_endpoint_con_nada_que_hacer_responde_ceros(
    internal, clock: dict[str, datetime], push: FakePushProvider
) -> None:
    clock["now"] = at(12, 0)
    assert internal().json() == {
        "checked": 0,
        "due": 0,
        "sent": 0,
        "retrying": 0,
        "failed": 0,
        "skipped": 0,
    }


def test_las_fechas_de_la_base_son_las_locales_no_las_utc(
    orm: DbSession, push: FakePushProvider, ana: User
) -> None:
    set_reminders(orm, ana, "23:30")
    run(orm, push, at(23, 45))
    assert orm.execute(text("select last_sent_on::text from reminder_settings")).scalar_one() == (
        "2026-10-26"
    )
