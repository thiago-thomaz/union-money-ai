"""Ponto de Entrada Cloud-First com Migração Segura, Health Gate, Backup Separado e Rollback Automático (Fase 5.1)."""

import os
import sys
import uvicorn
from app.automation.autonomous_orchestrator import UnionAutonomousOrchestrator
from app.config import settings
from app.core.cloud_runtime import (
    CloudAvailabilityMonitor,
    CloudDeployRegistry,
    CloudTaskWorker,
    SchedulerLeaderLock,
)
from app.core.logging import logger
from app.database import SessionLocal
from app.integrations.union_connect import UnionConnect
from migrations.migration_runner import run_migrations


def run_cloud_preflight_and_deploy_gate() -> dict:
    """Executa migrações seguras, eleição de líder, recuperação de workers, backup em /app/backups e health gate pós-deploy."""
    _ = settings.data_dir
    _ = settings.storage_dir
    _ = settings.backups_dir
    _ = settings.logs_dir

    run_migrations()

    with SessionLocal() as db:
        UnionConnect(db).load_persisted_runtime_credentials()
        leader_res = SchedulerLeaderLock.acquire_or_renew_leadership(db)
        worker_res = CloudTaskWorker(db).detect_and_recover_stalled_jobs()
        if leader_res.get("acquired", False):
            orch = UnionAutonomousOrchestrator(db)
            orch.execute_cycle("every_6_hours")
            orch.execute_cycle("daily")
        backup_res = CloudAvailabilityMonitor(db).run_separate_cloud_backup_and_test_restore(
            keep_last=settings.BACKUP_RETENTION_COUNT
        )
        deploy_res = CloudDeployRegistry(db).verify_post_deploy_and_rollback_if_unhealthy(
            version=settings.APP_VERSION,
            commit_sha=os.getenv("GIT_COMMIT_SHA") or os.getenv("SOURCE_COMMIT") or "production-cloud",
        )

    logger.info(
        "Cloud Preflight concluído: version=%s | deploy_status=%s | leader=%s | backup_ok=%s",
        settings.APP_VERSION,
        deploy_res.get("action"),
        leader_res.get("acquired"),
        backup_res.get("backup_verified"),
    )
    return {
        "leader": leader_res,
        "worker_recovery": worker_res,
        "backup": backup_res,
        "deploy_verification": deploy_res,
    }


def main() -> int:
    preflight = run_cloud_preflight_and_deploy_gate()
    deploy_info = preflight["deploy_verification"]
    if not deploy_info.get("healthy", False):
        logger.error("Critérios críticos de saúde falharam no deploy: %s", deploy_info)
        return 1

    if "--verify-only" in sys.argv:
        return 0

    port = int(os.getenv("PORT", str(settings.PORT)))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

