"""Script opcional para verificar ou restaurar o catálogo estrutural de categorias e marketplaces."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migrations.migration_runner import run_migrations


if __name__ == "__main__":
    run_migrations()
    print("Catálogo estrutural (10 categorias + 3 marketplaces + pesos padrão) verificado.")

