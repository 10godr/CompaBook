"""Errores de la API con el formato del contrato: {"error": {"code", "message", ...}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, **extra: object) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, error: ApiError) -> JSONResponse:
        body = {"code": error.code, "message": error.message, **error.extra}
        return JSONResponse(status_code=error.status_code, content={"error": body})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        # Solo el campo y el tipo de fallo: el valor recibido puede ser una contraseña.
        fields = [
            {"field": ".".join(str(part) for part in item["loc"][1:]), "type": item["type"]}
            for item in error.errors()
        ]
        body = {"code": "validation_error", "message": "Datos no válidos", "fields": fields}
        return JSONResponse(status_code=422, content={"error": body})
