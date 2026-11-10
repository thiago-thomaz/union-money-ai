"""Configuração de fixtures Pytest com banco SQLite isolado para testes."""

from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import Base
from app.dependencies import get_db_session
from app.main import app
from migrations.migration_runner import _ensure_structural_catalog


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Cria um banco SQLite temporário isolado por teste com catálogo estrutural."""
    settings.ENABLE_SCHEDULER = False
    test_db_file = tmp_path / "test_union_money.db"
    test_engine = create_engine(
        f"sqlite:///{test_db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    session = TestingSessionLocal()
    _ensure_structural_catalog(session)
    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Fornece TestClient FastAPI conectado à sessão de teste isolada."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db_session] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

