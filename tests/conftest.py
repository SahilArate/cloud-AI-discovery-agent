"""Fixtures shared by every test file."""

import pytest

from ai_discovery.config import get_settings
from ai_discovery.db.base import Base
from ai_discovery.db.session import _get_session_factory, get_engine

TEST_DATABASE_URL = "postgresql+psycopg://discovery:discovery@localhost:5432/ai_discovery_test"


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    _get_session_factory.cache_clear()


@pytest.fixture
def test_database(monkeypatch):
    """Point the app at the test database and start every test with empty tables."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    _clear_caches()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    _clear_caches()