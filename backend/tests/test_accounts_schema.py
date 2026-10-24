import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

TABLES = ["users", "allowed_emails", "sessions", "email_codes", "rate_limit_events"]


def add_user(db: Connection, email: str = "ana@example.com", language: str = "es") -> str:
    return db.execute(
        text(
            "insert into users (email, password_hash, language, timezone) "
            "values (:email, 'hash', :language, 'America/Santo_Domingo') returning id"
        ),
        {"email": email, "language": language},
    ).scalar_one()


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


def test_idioma_invalido(db: Connection) -> None:
    with pytest.raises(IntegrityError):
        add_user(db, language="fr")


def test_email_unico_sin_distinguir_mayusculas(db: Connection) -> None:
    add_user(db, "Ana@Example.com")
    with pytest.raises(IntegrityError):
        add_user(db, "ana@example.COM")


def test_correo_permitido_sin_distinguir_mayusculas(db: Connection) -> None:
    db.execute(text("insert into allowed_emails (email, note) values ('juan@example.com', 'Juan')"))
    found = db.execute(
        text("select note from allowed_emails where email = 'JUAN@Example.com'")
    ).scalar_one_or_none()
    assert found == "Juan"


def test_borrar_usuario_borra_sesiones_y_codigos(db: Connection) -> None:
    user_id = add_user(db)
    db.execute(
        text(
            "insert into sessions (user_id, token_hash, expires_at) "
            "values (:id, 'hash-de-token', now() + interval '30 days')"
        ),
        {"id": user_id},
    )
    db.execute(
        text(
            "insert into email_codes (user_id, purpose, code_hash, expires_at) "
            "values (:id, 'verify_email', 'hash-de-codigo', now() + interval '10 minutes')"
        ),
        {"id": user_id},
    )
    db.execute(text("delete from users where id = :id"), {"id": user_id})
    assert db.execute(text("select count(*) from sessions")).scalar_one() == 0
    assert db.execute(text("select count(*) from email_codes")).scalar_one() == 0


def test_proposito_de_codigo_invalido(db: Connection) -> None:
    user_id = add_user(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "insert into email_codes (user_id, purpose, code_hash, expires_at) "
                "values (:id, 'otro', 'h', now())"
            ),
            {"id": user_id},
        )


def test_token_de_sesion_unico(db: Connection) -> None:
    user_id = add_user(db)
    sql = text(
        "insert into sessions (user_id, token_hash, expires_at) "
        "values (:id, 'mismo', now() + interval '1 day')"
    )
    db.execute(sql, {"id": user_id})
    with pytest.raises(IntegrityError):
        db.execute(sql, {"id": user_id})


def test_eventos_de_limite_con_fecha(db: Connection) -> None:
    db.execute(text("insert into rate_limit_events (bucket, key) values ('login_ip', '1.2.3.4')"))
    created = db.execute(text("select created_at from rate_limit_events")).scalar_one()
    assert created is not None
