"""Utilitário de Backup e Verificação de Integridade para Banco SQLite, Configurações e Conteúdos (Seção 7)."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.core.logging import logger


def compute_sha256(file_path: Path) -> str:
    """Calcula o hash SHA-256 de um arquivo."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_backup_integrity(backup_path: Path) -> Dict[str, Any]:
    """Executa PRAGMA integrity_check e verifica tamanho/checksum do arquivo de backup SQLite."""
    if not backup_path.exists() or backup_path.stat().st_size == 0:
        return {
            "is_valid": False,
            "integrity_check": "FILE_MISSING_OR_EMPTY",
            "size_bytes": 0,
            "sha256": None,
        }
    conn = sqlite3.connect(str(backup_path))
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
        pragma_res = str(row[0]) if row else "unknown"
    finally:
        conn.close()

    is_ok = pragma_res.lower() == "ok"
    return {
        "is_valid": is_ok,
        "integrity_check": pragma_res,
        "size_bytes": backup_path.stat().st_size,
        "sha256": compute_sha256(backup_path) if is_ok else None,
    }


def _export_sanitized_settings_and_contents(backup_folder: Path, timestamp: str) -> Dict[str, str]:
    """Exporta configurações públicas (sem segredos/credenciais) e manifesto de conteúdos publicados."""
    safe_config = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "app_name": settings.APP_NAME,
        "site_name": settings.SITE_NAME,
        "app_version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "long_term_patrimony_goal_brl": settings.LONG_TERM_PATRIMONY_GOAL_BRL,
        "default_scoring_weights": settings.DEFAULT_SCORING_WEIGHTS,
        "default_autopilot_frequencies": settings.DEFAULT_AUTOPILOT_FREQUENCIES,
        "secrets_included": False,
    }
    settings_file = backup_folder / f"union_settings_{timestamp}.json"
    settings_file.write_text(json.dumps(safe_config, ensure_ascii=False, indent=2), encoding="utf-8")

    storage_files = []
    if settings.storage_dir.exists():
        for f in settings.storage_dir.rglob("*"):
            if f.is_file():
                storage_files.append(
                    {
                        "relative_path": str(f.relative_to(settings.storage_dir)),
                        "size_bytes": f.stat().st_size,
                    }
                )
    contents_file = backup_folder / f"union_contents_{timestamp}.json"
    contents_file.write_text(
        json.dumps(
            {
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "storage_files_count": len(storage_files),
                "files": storage_files,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "settings_path": str(settings_file),
        "contents_manifest_path": str(contents_file),
    }


def cleanup_old_backups(target_dir: Optional[Path] = None, keep_last: int = 10) -> int:
    """Remove backups antigos mantendo os N mais recentes conforme política configurável."""
    backup_folder = target_dir or (settings.data_dir / "backups")
    if not backup_folder.exists():
        return 0
    db_files = sorted(
        backup_folder.glob("union_money_ai_backup_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for old_file in db_files[max(1, keep_last) :]:
        try:
            old_file.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def create_sqlite_backup(
    target_dir: Optional[Path] = None,
    db: Optional[Session] = None,
    backup_type: str = "DAILY",
) -> Path:
    """Realiza backup atômico online do banco SQLite, exporta configurações sem segredos e valida integridade."""
    backup_folder = target_dir or (settings.data_dir / "backups")
    backup_folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_folder / f"union_money_ai_backup_{timestamp}.db"

    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        source_path = Path(db_url.replace("sqlite:///", "", 1))
    else:
        source_path = settings.data_dir / "union_money_ai.db"

    if not source_path.exists():
        conn = sqlite3.connect(str(source_path))
        conn.close()

    src_conn = sqlite3.connect(str(source_path))
    dst_conn = sqlite3.connect(str(backup_path))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        logger.info("Backup do banco de dados criado em: %s", backup_path)
    finally:
        dst_conn.close()
        src_conn.close()

    exported_meta = _export_sanitized_settings_and_contents(backup_folder, timestamp)
    integrity = verify_backup_integrity(backup_path)

    if db is not None and integrity["is_valid"]:
        try:
            from app.models.compliance import BackupRecord

            rec = BackupRecord(
                backup_filename=backup_path.name,
                db_backup_path=str(backup_path),
                settings_backup_path=exported_meta["settings_path"],
                contents_backup_path=exported_meta["contents_manifest_path"],
                sha256_checksum=integrity["sha256"] or "",
                size_bytes=integrity["size_bytes"],
                integrity_verified=True,
            )
            db.add(rec)
            db.commit()
        except Exception as exc:
            logger.warning("Não foi possível registrar BackupRecord no banco: %s", exc)

    return backup_path


if __name__ == "__main__":
    path = create_sqlite_backup()
    check = verify_backup_integrity(path)
    print(f"Backup concluído: {path} | Integridade: {check['integrity_check']} | SHA256: {check['sha256']}")
