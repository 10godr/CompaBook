import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

TABLES = ["concept_cards", "concepts", "processing_jobs"]


def add_user(db: Connection) -> str:
    return db.execute(
        text(
            "insert into users (email, password_hash, language, timezone) "
            "values ('ana@example.com', 'hash', 'es', 'UTC') returning id"
        )
    ).scalar_one()


def add_concept(db: Connection, user_id: str) -> str:
    return db.execute(
        text(
            "insert into concepts (user_id, title, language) "
            "values (:id, 'CI/CD', 'es') returning id"
        ),
        {"id": user_id},
    ).scalar_one()


def add_job(db: Connection, user_id: str, concept_id: str, **columns: str) -> None:
    names = ", ".join(["user_id", "concept_id", *columns])
    values = ", ".join([":user_id", ":concept_id", *(f":{name}" for name in columns)])
    db.execute(
        text(f"insert into processing_jobs ({names}) values ({values})"),
        {"user_id": user_id, "concept_id": concept_id, **columns},
    )


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


def test_un_concepto_nuevo_nace_sin_ficha_y_con_origen_app(db: Connection) -> None:
    concept_id = add_concept(db, add_user(db))
    row = db.execute(
        text("select card_id, source from concepts where id = :id"), {"id": concept_id}
    ).one()
    assert row == (None, "app")


def test_un_concepto_tiene_un_solo_trabajo(db: Connection) -> None:
    user_id = add_user(db)
    concept_id = add_concept(db, user_id)
    add_job(db, user_id, concept_id)
    with pytest.raises(IntegrityError):
        add_job(db, user_id, concept_id)


@pytest.mark.parametrize(
    "column, value", [("status", "dormido"), ("stage", "casi")], ids=["estado", "etapa"]
)
def test_estado_y_etapa_del_trabajo_solo_admiten_los_valores_definidos(
    db: Connection, column: str, value: str
) -> None:
    user_id = add_user(db)
    with pytest.raises(IntegrityError):
        add_job(db, user_id, add_concept(db, user_id), **{column: value})


def test_ficha_unica_por_clave_e_idioma(db: Connection) -> None:
    insert = text(
        "insert into concept_cards (canonical_title, cache_slug, language, what_is, what_for, "
        "example, model) values ('CI/CD', 'ci-cd', :language, 'a', 'b', 'c', 'm')"
    )
    db.execute(insert, {"language": "es"})
    db.execute(insert, {"language": "en"})
    with pytest.raises(IntegrityError):
        db.execute(insert, {"language": "es"})
