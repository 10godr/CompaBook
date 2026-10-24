from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def check_timezone(value: str) -> str:
    """Acepta solo zonas horarias reales (p. ej. «America/Santo_Domingo»)."""
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError) as error:
        raise ValueError("zona horaria desconocida") from error
    return value
