from fastapi import Header, Request

from app.errors import ApiError


def require_csrf_header(x_requested_with: str | None = Header(default=None)) -> None:
    """Todo POST/PUT/PATCH/DELETE exige `X-Requested-With: compabook` (diseno-tecnico.md §2.4).

    Un formulario de otro sitio no puede añadir esa cabecera.
    """
    if x_requested_with != "compabook":
        raise ApiError(403, "csrf", "Falta la cabecera X-Requested-With")


def client_ip(request: Request) -> str:
    """IP del cliente: el primer valor de `x-forwarded-for`, que pone Vercel."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "desconocida"
