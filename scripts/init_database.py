"""Script de Inicialização de Diretórios, Verificação de Dependências e Migrações do Banco (Seção 10)."""

import importlib
import sys
from typing import Dict, List
from app.config import settings
from migrations.migration_runner import run_migrations


REQUIRED_MODULES = (
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "jinja2",
    "apscheduler",
    "httpx",
    "bs4",
    "PIL",
    "imageio_ffmpeg",
    "reportlab",
    "bcrypt",
)


def verify_dependencies() -> Dict[str, bool]:
    """Verifica se todas as bibliotecas necessárias estão instaladas e disponíveis."""
    status_map: Dict[str, bool] = {}
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
            status_map[mod] = True
        except ImportError:
            status_map[mod] = False
    return status_map


def initialize_environment() -> Dict[str, object]:
    """Verifica dependências, cria diretórios obrigatórios e inicializa o banco SQLite."""
    deps = verify_dependencies()
    missing: List[str] = [k for k, ok in deps.items() if not ok]
    if missing:
        raise RuntimeError(f"Dependências ausentes: {', '.join(missing)}")

    dirs_created = [
        str(settings.data_dir),
        str(settings.logs_dir),
        str(settings.storage_dir),
    ]
    run_migrations()
    return {
        "status": "INITIALIZED",
        "python_version": sys.version.split()[0],
        "dependencies_ok": True,
        "directories": dirs_created,
        "database_url": settings.DATABASE_URL,
    }


if __name__ == "__main__":
    result = initialize_environment()
    print(f"UNION MONEY AI inicializado com sucesso: {result}")

