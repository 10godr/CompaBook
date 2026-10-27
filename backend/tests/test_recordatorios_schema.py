"""Esquema de la migración 0005: ajustes de recordatorio y dispositivos suscritos."""

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

TABLES = ["reminder_settings", "push_subscriptions"]


def add_user(db: Connection, email: str = "ana@example.com") -> str:
    return db.execute(
        text(
            "insert into users (email, password_hash, language, timezone) "
            "values (:email, 'hash', 'es', 'UTC') returning id"
        ),
        {"email": email},
    ).scalar_one()


def add_settings(db: Connection, user_id: str, **columns: object) -> None:
    names = ", ".join(["user_id", *columns])
    values = ", ".join([":user_id", *(f":{name}" for name in columns)])
    db.execute(
        text(f"insert into reminder_settings ({names}) values ({values})"),
        {"user_id": user_id, **columns},
    )


def add_subscription(
    db: Connection, user_id: str, endpoint: str = "https://x/1", **columns: object
):
    values = {"endpoint": endpoint, "p256dh": "clave", "auth": "secreto", **columns}
    names = ", ".join(["user_id", *values])
    placeholders = ", ".join([":user_id", *(f":{name}" for name in values)])
    db.execute(
        text(f"insert into push_subscriptions ({names}) values ({placeholders})"),
        {"user_id": user_id, **values},
    )


def count(db: Connection, table: str) -> int:
    return db.execute(text(f"select count(*) from {table}")).scalar_one()


def test_las_tablas_tienen_rls_sin_politicas(db: Connection) -> None:
    rows = db.execute(
        text("select relname, relrowsecurity from pg_class where relname = any(:names)"),
        {"names": TABLES},
    ).all()
    assert {name for name, _ in rows} == set(TABLES)
    assert all(enabled for _, enabled in rows)
    policies = db.execute(
        text("select count(*) from pg_policies where tablename = any(:names)"), {"names": TABLES}
    ).scalar_one()
    assert policies == 0


def test_los_ajustes_nuevos_parten_apagados_a_las_20_todos_los_dias(db: Connection) -> None:
    user_id = add_user(db)
    add_settings(db, user_id)
    row = db.execute(
        text("select enabled, local_time, weekdays, last_sent_on from reminder_settings")
    ).one()
    assert row.enabled is False
    assert row.local_time.isoformat() == "20:00:00"
    assert row.weekdays == [1, 2, 3, 4, 5, 6, 7]
    assert row.last_sent_on is None


def test_hay_unos_ajustes_por_usuario(db: Connection) -> None:
    user_id = add_user(db)
    add_settings(db, user_id)
    with pytest.raises(IntegrityError):
        add_settings(db, user_id)


def test_los_ajustes_necesitan_un_usuario_que_exista(db: Connection) -> None:
    with pytest.raises(IntegrityError):
        add_settings(db, "00000000-0000-0000-0000-000000000000")


@pytest.mark.parametrize("weekdays", ["{1}", "{7}", "{1,3,5}", "{1,2,3,4,5,6,7}"])
def test_los_dias_validos_se_aceptan(db: Connection, weekdays: str) -> None:
    add_settings(db, add_user(db), weekdays=weekdays)
    assert count(db, "reminder_settings") == 1


@pytest.mark.parametrize("weekdays", ["{}", "{0}", "{8}", "{1,8}", "{-1}"])
def test_los_dias_deben_ser_de_1_a_7_y_haber_alguno(db: Connection, weekdays: str) -> None:
    with pytest.raises(IntegrityError):
        add_settings(db, add_user(db), weekdays=weekdays)


def test_el_dispositivo_activo_por_defecto(db: Connection) -> None:
    add_subscription(db, add_user(db))
    assert db.execute(text("select active from push_subscriptions")).scalar_one() is True


def test_el_endpoint_es_unico_entre_todos_los_usuarios(db: Connection) -> None:
    ana, beto = add_user(db), add_user(db, "beto@example.com")
    add_subscription(db, ana, "https://x/1")
    add_subscription(db, ana, "https://x/2")  # un usuario puede tener varios dispositivos
    with pytest.raises(IntegrityError):
        add_subscription(db, beto, "https://x/1")  # un dispositivo no es de dos usuarios


@pytest.mark.parametrize(
    "columns",
    [
        {"endpoint": ""},
        {"endpoint": "x" * 2049},
        {"p256dh": ""},
        {"p256dh": "x" * 513},
        {"auth": ""},
        {"auth": "x" * 513},
        {"user_agent": "x" * 513},
    ],
)
def test_los_campos_del_dispositivo_tienen_limites(
    db: Connection, columns: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        add_subscription(db, add_user(db), **columns)


def test_los_limites_se_pueden_alcanzar_justo(db: Connection) -> None:
    add_subscription(db, add_user(db), endpoint="x" * 2048, p256dh="y" * 512, user_agent="z" * 512)
    assert count(db, "push_subscriptions") == 1


def test_borrar_el_usuario_borra_sus_ajustes_y_dispositivos(db: Connection) -> None:
    ana, beto = add_user(db), add_user(db, "beto@example.com")
    for user_id, endpoint in ((ana, "https://x/ana"), (beto, "https://x/beto")):
        add_settings(db, user_id)
        add_subscription(db, user_id, endpoint)
    db.execute(text("delete from users where id = :id"), {"id": ana})
    assert db.execute(text("select user_id from reminder_settings")).scalars().all() == [beto]
    assert db.execute(text("select endpoint from push_subscriptions")).scalars().all() == [
        "https://x/beto"
    ]
