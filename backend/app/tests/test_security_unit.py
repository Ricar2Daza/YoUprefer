from jose import jwt

from app.core import security
from app.core.config import settings


def test_get_password_hash_and_verify_password():
    hashed = security.get_password_hash("password123")
    assert isinstance(hashed, str)
    assert hashed != "password123"
    assert security.verify_password("password123", hashed) is True
    assert security.verify_password("wrong", hashed) is False


def test_verify_password_unknown_hash_returns_false():
    assert security.verify_password("password123", "not-a-hash") is False


def test_create_access_token_has_expected_claims():
    token = security.create_access_token("123")
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "123"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_create_refresh_token_has_expected_claims():
    token = security.create_refresh_token(456)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "456"
    assert payload["type"] == "refresh"
    assert "exp" in payload

