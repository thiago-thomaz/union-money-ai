"""Script de Restauração Segura de Backup SQLite com Verificação de Integridade (Seção 7)."""

from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, Optional
from app.config import settings
from app.core.logging import logger
from scripts.backup_db import verify_backup_integrity


def restore_sqlite_backup(
    backup_path: Path,
    target_db_path: Optional[Path] = None,
    expected_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Valida a integridade de um arquivo de backup e restaura-o sobre o banco de dados de destino."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Arquivo de backup não encontrado: {backup_path}")

    check = verify_backup_integrity(backup_path)
    if not check["is_valid"]:
        raise ValueError(f"Backup inválido ou corrompido: {check['integrity_check']}")

    if expected_sha256 and check["sha256"] != expected_sha256:
        raise ValueError(
            f"Checksum SHA-256 divergente! Esperado: {expected_sha256}, Obtido: {check['sha256']}"
        )

    if target_db_path is None:
        db_url = settings.DATABASE_URL
        if db_url.startswith("sqlite:///"):
            target_db_path = Path(db_url.replace("sqlite:///", "", 1))
        else:
            target_db_path = settings.data_dir / "union_money_ai.db"

    target_db_path.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(backup_path))
    dst_conn = sqlite3.connect(str(target_db_path))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        logger.info("Banco de dados restaurado com sucesso a partir de: %s", backup_path)
    finally:
        dst_conn.close()
        src_conn.close()

    post_check = verify_backup_integrity(target_db_path)
    return {
        "status": "RESTORED",
        "source_backup": str(backup_path),
        "target_db": str(target_db_path),
        "integrity_check": post_check["integrity_check"],
        "sha256": post_check["sha256"],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.restore_db <caminho_do_arquivo_backup.db>")
        sys.exit(1)
    res = restore_sqlite_backup(Path(sys.argv[1]))
    print(f"Restauração concluída: {res}")

