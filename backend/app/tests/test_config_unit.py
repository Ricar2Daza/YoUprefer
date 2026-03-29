import pytest

from app.core.config import Settings


def test_database_url_strips_quotes_and_bom():
    s = Settings(DATABASE_URL=' \ufeff"postgresql://u:p@h/db" ')
    assert s.DATABASE_URL == "postgresql://u:p@h/db"


def test_database_url_rejects_sqlite():
    with pytest.raises(ValueError):
        Settings(DATABASE_URL="sqlite:///./test.db")


def test_cors_origins_parses_json_list_string():
    s = Settings(BACKEND_CORS_ORIGINS='["http://localhost:3000","http://localhost:3001"]')
    assert [str(x) for x in s.BACKEND_CORS_ORIGINS] == ["http://localhost:3000", "http://localhost:3001"]

