import re
import uuid

import pytest

from app import security
from app.config import get_settings
from app.security import WeakPassword


@pytest.fixture
def secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "secret_key", "clave-de-prueba")


# --- Política de contraseñas ---


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("corta1", "too_short"),
        ("a" * 129, "too_long"),
        ("PassWord123", "too_common"),
        ("12345678", "too_common"),
        ("aaaaaaaaaa", "too_common"),
        ("contraseña", "too_common"),
    ],
)
def test_contrasena_rechazada(password: str, code: str) -> None:
    with pytest.raises(WeakPassword) as error:
        security.validate_password(password)
    assert error.value.code == code


@pytest.mark.parametrize(
    "password",
    ["caballo-grapa-azul", "abcd" * 32, "Mi clave 2026!"],  # 128 caracteres: el máximo
)
def test_contrasena_valida(password: str) -> None:
    security.validate_password(password)


# --- argon2id ---


def test_hash_argon2id_y_verificacion() -> None:
    password_hash = security.hash_password("caballo-grapa-azul")
    assert password_hash.startswith("$argon2id$")
    assert security.verify_password("caballo-grapa-azul", password_hash) is True
    assert security.verify_password("otra-clave-distinta", password_hash) is False


def test_cada_hash_lleva_su_sal() -> None:
    assert security.hash_password("misma-clave-1") != security.hash_password("misma-clave-1")


def test_usuario_inexistente_falla_sin_error() -> None:
    assert security.verify_password("lo-que-sea-123", None) is False


# --- Tokens de sesión ---


def test_token_de_sesion() -> None:
    token, token_hash = security.new_session_token()
    assert len(token) >= 43  # 32 bytes en base64 url
    assert re.fullmatch(r"[0-9a-f]{64}", token_hash)
    assert token not in token_hash
    assert security.hash_token(token) == token_hash


def test_los_tokens_no_se_repiten() -> None:
    assert security.new_session_token()[0] != security.new_session_token()[0]


# --- Códigos por correo ---


def test_codigo_de_seis_digitos() -> None:
    for _ in range(200):
        assert re.fullmatch(r"\d{6}", security.new_code())


def test_codigo_verificable(secret_key: None) -> None:
    user_id = uuid.uuid4()
    code_hash = security.hash_code("012345", user_id, "verify_email")
    assert "012345" not in code_hash
    assert security.verify_code("012345", user_id, "verify_email", code_hash) is True
    assert security.verify_code("012346", user_id, "verify_email", code_hash) is False


def test_codigo_ligado_a_usuario_y_proposito(secret_key: None) -> None:
    user_id = uuid.uuid4()
    code_hash = security.hash_code("012345", user_id, "verify_email")
    assert security.verify_code("012345", uuid.uuid4(), "verify_email", code_hash) is False
    assert security.verify_code("012345", user_id, "reset_password", code_hash) is False


def test_el_hash_del_codigo_depende_de_la_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    monkeypatch.setattr(get_settings(), "secret_key", "clave-a")
    hash_a = security.hash_code("012345", user_id, "verify_email")
    monkeypatch.setattr(get_settings(), "secret_key", "clave-b")
    assert security.hash_code("012345", user_id, "verify_email") != hash_a


def test_sin_secret_key_no_se_generan_codigos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "secret_key", None)
    with pytest.raises(RuntimeError):
        security.hash_code("012345", uuid.uuid4(), "verify_email")
