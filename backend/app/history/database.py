"""SQLite-backed persistence for workout history. One engine/session
factory, module-level for reuse across requests; get_session() is a
FastAPI dependency yielding one Session per request.

DEFAULT_DB_PATH is computed relative to this file so it resolves
correctly both locally (backend/data/formiq.db) and inside the Docker
image, where backend/app is copied to /app/app (three parents up from
here is /app, giving /app/data/formiq.db — see
infra/docker/backend.Dockerfile).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "formiq.db"


class Base(DeclarativeBase):
    pass


def build_engine(db_path: Path) -> Engine:
    """Create a SQLite engine at db_path, creating its parent directory
    if missing (SQLite requires the directory to exist before it can
    open/create the file)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


engine = build_engine(DEFAULT_DB_PATH)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables that don't already exist. Called once at app
    startup (see app.main's lifespan)."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: one Session per request, closed afterward."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
