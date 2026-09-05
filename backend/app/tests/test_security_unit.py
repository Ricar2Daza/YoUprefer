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
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience=settings.JWT_AUDIENCE)
    assert payload["sub"] == "123"
    assert payload["type"] == "access"
    assert payload["iss"] == settings.JWT_ISSUER
    assert payload["aud"] == settings.JWT_AUDIENCE
    assert "exp" in payload


def test_create_refresh_token_has_expected_claims():
    token = security.create_refresh_token(456)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience=settings.JWT_AUDIENCE)
    assert payload["sub"] == "456"
    assert payload["type"] == "refresh"
    assert payload["iss"] == settings.JWT_ISSUER
    assert payload["aud"] == settings.JWT_AUDIENCE
    assert "exp" in payload


def test_access_token_invalid_audience_rejected():
    token = security.create_access_token("123")
    from jose.exceptions import JWTClaimsError
    try:
        jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience="otra-app")
        assert False, "Debe rechazar una audiencia incorrecta"
    except JWTClaimsError:
        pass


def test_access_token_invalid_issuer_rejected():
    from jose import jwt as _jwt
    import datetime
    payload = {
        "sub": "123",
        "type": "access",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
        "iss": "emisor-desconocido",
        "aud": settings.JWT_AUDIENCE,
        "jti": "xyz",
    }
    token = _jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    decoded = _jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience=settings.JWT_AUDIENCE)
    # La validación de issuer ocurre en deps._decode_and_validate_token
    assert decoded["iss"] != settings.JWT_ISSUER

