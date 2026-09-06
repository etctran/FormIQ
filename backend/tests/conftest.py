"""Shared pytest fixtures: gives every test an isolated, per-test-function
SQLite DB by overriding the app's real history.database.get_session
dependency, so no test ever touches backend/data/formiq.db."""

import pytest
from sqlalchemy.orm import sessionmaker

from app.history.database import Base, build_engine, get_session
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_history_db(tmp_path):
    engine = build_engine(tmp_path / "test_history.db")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_session():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    yield
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()
