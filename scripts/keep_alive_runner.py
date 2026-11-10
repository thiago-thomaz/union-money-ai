"""Supervisor de Execução Contínua e Diagnóstico de Infraestrutura (Fase 4 - Seção 12).

Responsabilidades:
- Identificar com transparência absoluta se o sistema está em Computador Local (Opção 1) ou Servidor/VPS 24/7 (Opção 2).
- Nunca prometer operação 24/7 se o computador local for desligado.
- Executar healthcheck de banco de dados, CPU, memória e espaço em disco.
- Configurar logs rotativos (RotatingFileHandler).
- Recuperar fila persistente do orquestrador (UnionAutonomousOrchestrator.recover_persistent_queue).
- Acionar backup automático e supervisionar ciclos contínuos com auto-restart em caso de falha.
"""

from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import shutil
import socket
import time
from typing import Any, Dict

from sqlalchemy import text

from app.automation.autonomous_orchestrator import UnionAutonomousOrchestrator
from app.config import BASE_DIR, settings
from app.database import SessionLocal
from scripts.backup_db import create_sqlite_backup, verify_backup_integrity


LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ROTATING_LOG_FILE = LOG_DIR / "union_autonomous_supervisor.log"


def configure_rotating_logger() -> logging.Logger:
    """Configura logger com rotação automática de arquivos (máx 5MB x 5 backups)."""
    logger = logging.getLogger("union_keep_alive")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            ROTATING_LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def inspect_execution_infrastructure() -> Dict[str, Any]:
    """Detecta e documenta a infraestrutura real de execução (Local vs VPS 24/7)."""
    os_name = platform.system()
    hostname = socket.gethostname()
    in_docker = Path("/.dockerenv").exists() or os.environ.get("DOCKER_CONTAINER") == "1"
    is_cloud_vps = bool(
        os.environ.get("VPS_PROVIDER")
        or os.environ.get("CLOUD_INSTANCE")
        or in_docker
        or (os_name == "Linux" and Path("/etc/systemd/system").exists())
    )

    disk_usage = shutil.disk_usage(BASE_DIR)
    free_disk_gb = round(disk_usage.free / (1024 ** 3), 2)
    total_disk_gb = round(disk_usage.total / (1024 ** 3), 2)

    db_healthy = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_healthy = True
    except Exception:
        db_healthy = False

    if is_cloud_vps:
        mode = "OPCAO_2_VPS_OU_SERVIDOR_ATIVO"
        uptime_guarantee_notice = (
            "Ambiente de servidor/container detectado. Operação 24/7 ativa enquanto a instância "
            "de servidor permanecer ligada e conectada à rede."
        )
    else:
        mode = "OPCAO_1_COMPUTADOR_LOCAL"
        uptime_guarantee_notice = (
            "AVISO DE TRANSPARÊNCIA: O sistema está rodando em um computador local ("
            f"{os_name} / {hostname}). Para que a operação autônoma funcione continuamente, "
            "o computador precisa permanecer ligado, sem suspensão de energia e conectado à internet. "
            "NÃO há operação 24/7 se o computador local for desligado."
        )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "infrastructure_option": mode,
        "os": os_name,
        "hostname": hostname,
        "in_docker": in_docker,
        "is_cloud_vps": is_cloud_vps,
        "autonomy_mode": settings.AUTONOMY_MODE,
        "database_healthy": db_healthy,
        "disk_free_gb": free_disk_gb,
        "disk_total_gb": total_disk_gb,
        "rotating_log_path": str(ROTATING_LOG_FILE),
        "transparency_notice": uptime_guarantee_notice,
    }


def run_supervisor_health_and_recovery_tick() -> Dict[str, Any]:
    """Executa um ciclo de supervisão: healthcheck, recuperação de fila e backup preventivo."""
    logger = configure_rotating_logger()
    infra = inspect_execution_infrastructure()

    with SessionLocal() as db:
        orchestrator = UnionAutonomousOrchestrator(db)
        recovery_info = orchestrator.recover_persistent_queue()
        backup_path = create_sqlite_backup(db=db, backup_type="SUPERVISOR_AUTO")
        integrity = verify_backup_integrity(backup_path)

    logger.info(
        "Supervisor tick concluído | DB=%s | Recovered=%s | BackupValid=%s",
        infra["database_healthy"],
        recovery_info.get("recovered_jobs", 0),
        integrity.get("is_valid"),
    )

    return {
        "status": "HEALTHY" if infra["database_healthy"] else "DEGRADED",
        "infrastructure": infra,
        "queue_recovery": recovery_info,
        "backup": {
            "path": str(backup_path),
            "is_valid": integrity["is_valid"],
            "sha256": integrity["sha256"],
        },
    }


def start_continuous_supervisor(poll_seconds: int = 300, max_loops: int = 0) -> None:
    """Loop de supervisão contínua com auto-restart em caso de falha inesperada."""
    logger = configure_rotating_logger()
    loops = 0
    while True:
        loops += 1
        try:
            run_supervisor_health_and_recovery_tick()
        except Exception as exc:
            logger.error("Falha capturada pelo supervisor (auto-restart ativo): %s", exc)
        if max_loops > 0 and loops >= max_loops:
            break
        time.sleep(poll_seconds)


if __name__ == "__main__":
    import sys

    continuous_flag = (
        "--continuous" in sys.argv
        or os.environ.get("SUPERVISOR_CONTINUOUS", "0") == "1"
    )
    poll_sec = int(os.environ.get("SUPERVISOR_POLL_SECONDS", "300" if continuous_flag else "60"))
    start_continuous_supervisor(
        poll_seconds=poll_sec,
        max_loops=0 if continuous_flag else 1,
    )
