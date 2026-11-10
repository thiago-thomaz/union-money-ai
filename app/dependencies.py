"""Injeção de dependências da aplicação."""

from typing import Generator
from sqlalchemy.orm import Session
from app.database import get_db


def get_db_session() -> Generator[Session, None, None]:
    """Alias explícito para obtenção de sessão de banco."""
    yield from get_db()

