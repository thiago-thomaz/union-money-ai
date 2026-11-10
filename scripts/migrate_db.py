"""Script CLI para execução de migrações de banco de dados."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migrations.migration_runner import run_migrations


if __name__ == "__main__":
    run_migrations()
    print("Migrações aplicadas com sucesso.")

