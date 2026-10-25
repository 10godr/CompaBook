"""Esquema de la migración 0004: alias, caché de videos y consulta de YouTube."""

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

TABLES = ["concept_aliases", "video_cache"]


def add_card(db: Connection, slug: str = "ci-cd", language: str = "es") -> None:
    db.execute(
        text(
            "insert into concept_cards "
            "(canonical_title, cache_slug, language, what_is, what_for, example, model) "
            "values ('CI/CD', :slug, :language, 'a', 'b', 'c', 'modelo')"
        ),
        {"slug": slug, "language": language},
    )


def add_alias(db: Connection, alias: str, slug: str = "ci-cd", language: str = "es") -> None:
    db.execute(
        text("insert into concept_aliases (language, alias, cache_slug) values (:l, :a, :s)"),
        {"l": language, "a": alias, "s": slug},
    )


def add_video(db: Connection, position: int, slug: str = "ci-cd", language: str = "es") -> None:
    db.execute(
        text(
            "insert into video_cache "
            "(cache_slug, language, position, youtube_id, title, thumbnail_url) "
            "values (:s, :l, :p, 'abc', 'Título', 'https://i.ytimg.com/vi/abc/hqdefault.jpg')"
        ),
        {"s": slug, "l": language, "p": position},
    )


def count(db: Connection, table: str) -> int:
    return db.execute(text(f"select count(*) from {table}")).scalar_one()


def test_las_tablas_nuevas_tienen_rls_sin_politicas(db: Connection) -> None:
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


def test_ninguna_tabla_nueva_guarda_datos_de_un_usuario(db: Connection) -> None:
    columns = db.execute(
        text(
            "select table_name, column_name from information_schema.columns "
            "where table_name = any(:names) and column_name like '%user%'"
        ),
        {"names": TABLES},
    ).all()
    assert columns == []


def test_la_consulta_de_youtube_de_la_ficha_es_opcional(db: Connection) -> None:
    add_card(db)
    assert db.execute(text("select youtube_search_query from concept_cards")).scalar_one() is None


def test_un_alias_necesita_su_ficha(db: Connection) -> None:
    with pytest.raises(IntegrityError):
        add_alias(db, "ci cd")


def test_un_alias_lleva_a_la_ficha_del_mismo_idioma(db: Connection) -> None:
    add_card(db, language="es")
    with pytest.raises(IntegrityError):
        add_alias(db, "ci cd", language="en")  # no hay ficha `ci-cd` en inglés


def test_el_alias_es_unico_por_idioma(db: Connection) -> None:
    add_card(db, language="es")
    add_card(db, language="en")
    add_alias(db, "ci cd", language="es")
    add_alias(db, "ci cd", language="en")  # el mismo texto en otro idioma es otro alias
    assert count(db, "concept_aliases") == 2
    with pytest.raises(IntegrityError):
        add_alias(db, "ci cd", language="es")


@pytest.mark.parametrize("alias", ["", "x" * 61])
def test_un_alias_tiene_entre_1_y_60_caracteres(db: Connection, alias: str) -> None:
    add_card(db)
    with pytest.raises(IntegrityError):
        add_alias(db, alias)


def test_un_alias_de_60_caracteres_vale(db: Connection) -> None:
    add_card(db)
    add_alias(db, "x" * 60)
    assert count(db, "concept_aliases") == 1


def test_borrar_la_ficha_borra_sus_alias_pero_no_los_de_otra(db: Connection) -> None:
    add_card(db, slug="ci-cd")
    add_card(db, slug="docker")
    add_alias(db, "ci cd", slug="ci-cd")
    add_alias(db, "contenedores", slug="docker")
    db.execute(text("delete from concept_cards where cache_slug = 'ci-cd'"))
    assert db.execute(text("select alias from concept_aliases")).scalars().all() == ["contenedores"]


@pytest.mark.parametrize("position", [0, 3])
def test_solo_hay_dos_posiciones_de_video(db: Connection, position: int) -> None:
    add_video(db, 1)
    add_video(db, 2)
    with pytest.raises(IntegrityError):
        add_video(db, position)


def test_cada_posicion_de_video_es_unica_por_concepto_e_idioma(db: Connection) -> None:
    add_video(db, 1)
    add_video(db, 1, language="en")  # otro idioma: otra lista
    add_video(db, 1, slug="docker")  # otro concepto: otra lista
    with pytest.raises(IntegrityError):
        add_video(db, 1)


def test_el_idioma_de_los_videos_es_es_o_en(db: Connection) -> None:
    with pytest.raises(IntegrityError):
        add_video(db, 1, language="fr")
