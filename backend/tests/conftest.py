import os

import pytest
from sqlmodel import SQLModel, create_engine

from app import db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Isolated database so tests never touch backend/data/marketrecall.db.
    Set TEST_DATABASE_URL to run against a disposable Postgres instead of SQLite."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_engine(db.normalize_url(url), connect_args={"options": "-c timezone=GMT"})
        SQLModel.metadata.drop_all(engine)
    else:
        engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    yield engine
    engine.dispose()
