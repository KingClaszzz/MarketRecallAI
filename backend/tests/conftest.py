import pytest
from sqlmodel import SQLModel, create_engine

from app import db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Isolated SQLite database so tests never touch backend/data/marketrecall.db."""
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    return engine
