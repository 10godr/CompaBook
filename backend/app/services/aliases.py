"""Normalizar lo que escribe el usuario para buscarlo entre los alias (diseno-tecnico.md §5.5)."""

import unicodedata

ALIAS_MAX = 60


def normalize_title(title: str) -> str | None:
    """El título en minúsculas, sin tildes y con los espacios colapsados.

    «Integración  Continua » → «integracion continua». Devuelve None si no queda texto o si pasa
    de 60 caracteres: un título largo no crea ni busca alias (la ficha se genera igual y se
    comparte por su `cache_slug`).
    """
    decomposed = unicodedata.normalize("NFKD", title)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    normalized = " ".join(without_marks.lower().split())
    if not normalized or len(normalized) > ALIAS_MAX:
        return None
    return normalized
