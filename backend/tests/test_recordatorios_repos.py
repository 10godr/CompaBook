"""Repositorios de recordatorios y dispositivos: aislamiento y traspaso de dispositivo."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.models import PushSubscription, ReminderSettings, User
from app.repositories import PushSubscriptionRepository, ReminderRepository
from app.repositories.reminders import MAX_SUBSCRIPTIONS

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def add_user(orm: DbSession, email: str) -> User:
    user = User(email=email, password_hash="hash", language="es", timezone="UTC")
    orm.add(user)
    orm.flush()
    return user


@pytest.fixture
def two_users(orm: DbSession) -> tuple[User, User]:
    return add_user(orm, "ana@example.com"), add_user(orm, "beto@example.com")


def subscribe(
    orm: DbSession, user: User, endpoint: str, minutes: int = 0, user_agent: str | None = None
) -> PushSubscription:
    return PushSubscriptionRepository(orm, user.id).upsert(
        endpoint, "clave", "secreto", user_agent, NOW + timedelta(minutes=minutes)
    )


# --- Ajustes -------------------------------------------------------------------------------


def test_sin_guardar_nada_no_hay_ajustes(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, _ = two_users
    assert ReminderRepository(orm, ana.id).get() is None


def test_guardar_crea_los_ajustes(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, _ = two_users
    settings = ReminderRepository(orm, ana.id).save(True, time(7, 30), [1, 3, 5], NOW)
    assert (settings.enabled, settings.local_time, settings.weekdays) == (
        True,
        time(7, 30),
        [1, 3, 5],
    )
    assert settings.last_sent_on is None


def test_guardar_otra_vez_actualiza_la_misma_fila(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    repository = ReminderRepository(orm, ana.id)
    repository.save(True, time(7, 30), [1], NOW)
    settings = repository.save(False, time(21, 0), [2, 4], NOW + timedelta(minutes=5))
    assert (settings.enabled, settings.local_time, settings.weekdays) == (
        False,
        time(21, 0),
        [2, 4],
    )
    assert orm.scalars(select(ReminderSettings)).all() == [settings]


def test_los_dias_se_guardan_ordenados_y_sin_repetir(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    settings = ReminderRepository(orm, ana.id).save(True, time(20, 0), [5, 1, 5, 3, 1], NOW)
    assert settings.weekdays == [1, 3, 5]


def test_guardar_no_borra_el_ultimo_envio(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, _ = two_users
    repository = ReminderRepository(orm, ana.id)
    repository.save(True, time(20, 0), [1, 2, 3, 4, 5, 6, 7], NOW)
    orm.execute(
        update(ReminderSettings)
        .where(ReminderSettings.user_id == ana.id)
        .values(last_sent_on=date(2026, 10, 27))
    )
    settings = repository.save(True, time(21, 0), [1, 2], NOW)  # cambia la hora, no repite el aviso
    assert settings.last_sent_on == date(2026, 10, 27)


def test_cada_usuario_ve_solo_sus_ajustes(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, beto = two_users
    ReminderRepository(orm, ana.id).save(True, time(7, 0), [1], NOW)
    assert ReminderRepository(orm, beto.id).get() is None
    ReminderRepository(orm, beto.id).save(False, time(22, 0), [7], NOW)
    ana_settings = ReminderRepository(orm, ana.id).get()
    assert ana_settings is not None and ana_settings.local_time == time(7, 0)
    assert ana_settings.enabled is True


# --- Dispositivos --------------------------------------------------------------------------


def test_registrar_un_dispositivo_lo_deja_activo(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    subscription = subscribe(orm, ana, "https://push/1", user_agent="Safari")
    assert (subscription.user_id, subscription.endpoint, subscription.active) == (
        ana.id,
        "https://push/1",
        True,
    )
    assert subscription.user_agent == "Safari"
    assert [s.endpoint for s in PushSubscriptionRepository(orm, ana.id).list_active()] == [
        "https://push/1"
    ]


def test_registrar_dos_veces_el_mismo_dispositivo_no_lo_duplica_y_lo_reactiva(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    repository = PushSubscriptionRepository(orm, ana.id)
    subscribe(orm, ana, "https://push/1")
    repository.deactivate("https://push/1")
    assert repository.list_active() == []
    again = PushSubscriptionRepository(orm, ana.id).upsert(
        "https://push/1", "clave-nueva", "secreto-nuevo", None, NOW + timedelta(minutes=10)
    )
    assert (again.p256dh, again.auth, again.active) == ("clave-nueva", "secreto-nuevo", True)
    assert again.created_at == NOW + timedelta(minutes=10)
    assert len(orm.scalars(select(PushSubscription)).all()) == 1


def test_un_dispositivo_pasa_al_ultimo_usuario_que_se_suscribe(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    subscribe(orm, ana, "https://push/compartido")
    subscribe(orm, beto, "https://push/compartido", minutes=5)
    assert PushSubscriptionRepository(orm, ana.id).list_active() == []
    assert PushSubscriptionRepository(orm, ana.id).get("https://push/compartido") is None
    mine = PushSubscriptionRepository(orm, beto.id).list_active()
    assert [(s.endpoint, s.user_id) for s in mine] == [("https://push/compartido", beto.id)]
    assert len(orm.scalars(select(PushSubscription)).all()) == 1


def test_la_lista_solo_trae_los_activos_del_usuario_los_mas_nuevos_primero(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    subscribe(orm, ana, "https://push/viejo", minutes=0)
    subscribe(orm, ana, "https://push/nuevo", minutes=5)
    subscribe(orm, ana, "https://push/muerto", minutes=2)
    subscribe(orm, beto, "https://push/de-beto", minutes=3)
    repository = PushSubscriptionRepository(orm, ana.id)
    repository.deactivate("https://push/muerto")
    assert [s.endpoint for s in repository.list_active()] == [
        "https://push/nuevo",
        "https://push/viejo",
    ]


def test_hay_un_maximo_de_dispositivos_y_se_descartan_los_mas_viejos(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    subscribe(orm, beto, "https://push/de-beto")
    for n in range(MAX_SUBSCRIPTIONS + 2):
        subscribe(orm, ana, f"https://push/{n}", minutes=n)
    kept = [s.endpoint for s in PushSubscriptionRepository(orm, ana.id).list_active()]
    assert kept == [f"https://push/{n}" for n in reversed(range(2, MAX_SUBSCRIPTIONS + 2))]
    assert PushSubscriptionRepository(orm, beto.id).get("https://push/de-beto") is not None


def test_el_dispositivo_recien_registrado_nunca_se_descarta(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    for n in range(MAX_SUBSCRIPTIONS):
        subscribe(orm, ana, f"https://push/{n}", minutes=10 + n)
    # Registrado con una hora anterior a todos los demás (reloj desajustado): se queda igual.
    subscription = subscribe(orm, ana, "https://push/recien", minutes=0)
    assert subscription.endpoint == "https://push/recien"
    assert PushSubscriptionRepository(orm, ana.id).get("https://push/recien") is not None


def test_los_inactivos_se_descartan_antes_que_los_activos(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    repository = PushSubscriptionRepository(orm, ana.id)
    for n in range(MAX_SUBSCRIPTIONS):
        subscribe(orm, ana, f"https://push/{n}", minutes=n)
    repository.deactivate("https://push/4")  # el más nuevo, pero ya no existe
    subscribe(orm, ana, "https://push/nuevo", minutes=10)
    assert repository.get("https://push/4") is None
    assert repository.get("https://push/0") is not None


def test_dar_de_baja_borra_solo_el_dispositivo_propio(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    subscribe(orm, ana, "https://push/ana")
    subscribe(orm, beto, "https://push/beto")
    assert PushSubscriptionRepository(orm, ana.id).delete("https://push/beto") is False
    assert PushSubscriptionRepository(orm, beto.id).get("https://push/beto") is not None
    assert PushSubscriptionRepository(orm, ana.id).delete("https://push/ana") is True
    assert PushSubscriptionRepository(orm, ana.id).delete("https://push/ana") is False
    assert PushSubscriptionRepository(orm, ana.id).get("https://push/ana") is None


def test_desactivar_afecta_solo_al_dispositivo_propio(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, beto = two_users
    subscribe(orm, beto, "https://push/beto")
    assert PushSubscriptionRepository(orm, ana.id).deactivate("https://push/beto") is False
    assert [s.endpoint for s in PushSubscriptionRepository(orm, beto.id).list_active()] == [
        "https://push/beto"
    ]
    assert PushSubscriptionRepository(orm, ana.id).deactivate("https://push/no-existe") is False
