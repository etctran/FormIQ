from sqlalchemy import text

from app.history.database import build_engine


def test_build_engine_creates_missing_parent_directory(tmp_path) -> None:
    db_path = tmp_path / "nested" / "sub" / "test.db"
    assert not db_path.parent.exists()

    engine = build_engine(db_path)

    assert db_path.parent.exists()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    engine.dispose()


def test_build_engine_works_with_already_existing_directory(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    engine = build_engine(db_path)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    engine.dispose()
