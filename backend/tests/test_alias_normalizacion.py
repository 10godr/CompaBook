"""Normalización de títulos para los alias (diseno-tecnico.md §5.5)."""

import pytest

from app.services.aliases import ALIAS_MAX, normalize_title


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Integración  Continua ", "integracion continua"),
        ("CI/CD", "ci/cd"),
        ("ci/cd", "ci/cd"),
        ("  Docker\t\nCompose  ", "docker compose"),
        ("Árbol Binario", "arbol binario"),
        ("¿Qué es un Pingüino?", "¿que es un pinguino?"),
        ("ＤＯＣＫＥＲ", "docker"),  # letras de ancho completo
        ("ﬁle system", "file system"),  # ligadura
    ],
)
def test_normaliza_minusculas_tildes_y_espacios(title: str, expected: str) -> None:
    assert normalize_title(title) == expected


def test_las_distintas_formas_de_escribir_lo_mismo_coinciden() -> None:
    forms = ["Integración Continua", "integracion continua", "  INTEGRACIÓN   CONTINUA "]
    assert len({normalize_title(form) for form in forms}) == 1


def test_es_idempotente() -> None:
    once = normalize_title("  Árbol   Binario ")
    assert once is not None
    assert normalize_title(once) == once


@pytest.mark.parametrize("title", ["", "   ", "\n\t"])
def test_sin_texto_no_hay_alias(title: str) -> None:
    assert normalize_title(title) is None


def test_hasta_60_caracteres_vale_y_mas_no() -> None:
    assert normalize_title("a" * ALIAS_MAX) == "a" * ALIAS_MAX
    assert normalize_title("a" * (ALIAS_MAX + 1)) is None


def test_el_limite_se_mide_tras_normalizar() -> None:
    # 70 caracteres escritos, pero 59 tras colapsar los espacios sobrantes.
    title = "a" * 30 + " " * 12 + "b" * 28
    assert len(title) > ALIAS_MAX
    assert normalize_title(title) == "a" * 30 + " " + "b" * 28
