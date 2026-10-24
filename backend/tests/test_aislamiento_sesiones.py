"""Aislamiento entre usuarios (contexto.md §10.5): nadie ve ni toca datos ajenos."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session as DbSession

from app.models import Session, User
from app.repositories import SessionRepository

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def add_user(orm: DbSession, email: str) -> User:
    user = User(email=email, password_hash="hash", language="es", timezone="UTC")
    orm.add(user)
    orm.flush()
    return user


@pytest.fixture
def two_users(orm: DbSession) -> tuple[User, User]:
    ana = add_user(orm, "ana@example.com")
    beto = add_user(orm, "beto@example.com")
    SessionRepository(orm, ana.id).create("token-ana-1", NOW + timedelta(days=30))
    SessionRepository(orm, ana.id).create("token-ana-2", NOW + timedelta(days=30))
    SessionRepository(orm, beto.id).create("token-beto-1", NOW + timedelta(days=30))
    return ana, beto


def test_cada_usuario_solo_lista_sus_sesiones(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, beto = two_users
    assert {s.token_hash for s in SessionRepository(orm, ana.id).list_active(NOW)} == {
        "token-ana-1",
        "token-ana-2",
    }
    assert [s.token_hash for s in SessionRepository(orm, beto.id).list_active(NOW)] == [
        "token-beto-1"
    ]


def test_no_se_puede_cerrar_la_sesion_de_otro(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, beto = two_users
    session_of_beto = SessionRepository(orm, beto.id).list_active(NOW)[0]
    assert SessionRepository(orm, ana.id).revoke(session_of_beto.id) is False
    assert len(SessionRepository(orm, beto.id).list_active(NOW)) == 1


def test_una_sesion_que_no_existe_se_comporta_igual_que_una_ajena(
    orm: DbSession, two_users: tuple[User, User]
) -> None:
    ana, _ = two_users
    assert SessionRepository(orm, ana.id).revoke(uuid.uuid4()) is False


def test_cerrar_las_propias(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, beto = two_users
    session_of_ana = SessionRepository(orm, ana.id).list_active(NOW)[0]
    assert SessionRepository(orm, ana.id).revoke(session_of_ana.id) is True
    assert len(SessionRepository(orm, ana.id).list_active(NOW)) == 1
    assert len(SessionRepository(orm, beto.id).list_active(NOW)) == 1


def test_cerrar_todas_no_toca_las_de_otro(orm: DbSession, two_users: tuple[User, User]) -> None:
    ana, beto = two_users
    assert SessionRepository(orm, ana.id).revoke_all() == 2
    assert SessionRepository(orm, ana.id).list_active(NOW) == []
    assert len(SessionRepository(orm, beto.id).list_active(NOW)) == 1


def test_las_sesiones_caducadas_no_cuentan(orm: DbSession) -> None:
    ana = add_user(orm, "ana@example.com")
    repo = SessionRepository(orm, ana.id)
    repo.create("vieja", NOW - timedelta(seconds=1))
    repo.create("vigente", NOW + timedelta(days=1))
    assert [s.token_hash for s in repo.list_active(NOW)] == ["vigente"]


def test_el_repositorio_guarda_el_user_id_de_la_sesion(orm: DbSession) -> None:
    ana = add_user(orm, "ana@example.com")
    created = SessionRepository(orm, ana.id).create("t", NOW + timedelta(days=1), "iPhone")
    stored = orm.get(Session, created.id)
    assert stored is not None
    assert stored.user_id == ana.id
    assert stored.user_agent == "iPhone"
