"""Rotas de Infraestrutura Cloud-First, Deploy Automático, Liderança de Scheduler, Worker e Backup (Fase 5.1)."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.config import settings
from app.core.cloud_runtime import (
    CloudAvailabilityMonitor,
    CloudDeployRegistry,
    CloudTaskWorker,
    SchedulerLeaderLock,
)
from app.dependencies import get_db_session as get_db

router = APIRouter(prefix="/api/cloud", tags=["Fase 5.1 — Cloud First & Auto-Deploy"])


class DeployVerifyPayload(BaseModel):
    version: Optional[str] = None
    commit_sha: Optional[str] = None
    simulate_health_failure: bool = False


@router.get("/status")
def get_cloud_architecture_status(db: Session = Depends(get_db)):
    """Retorna o status completo dos 6 componentes separados da arquitetura de produção Cloud-First."""
    return CloudAvailabilityMonitor(db).get_production_architecture_status()


@router.get("/leader")
def get_scheduler_leader_status(db: Session = Depends(get_db)):
    """Retorna o status da trava distribuída de líder do Scheduler (impede duplicidade de tarefas)."""
    return SchedulerLeaderLock.get_leader_status(db)


@router.post("/worker/recover")
def trigger_cloud_worker_recovery(
    timeout_minutes: int = Query(default=25, ge=1, le=240),
    db: Session = Depends(get_db),
):
    """Detecta e recupera tarefas travadas com controle de timeout e backoff exponencial."""
    return CloudTaskWorker(db, task_timeout_minutes=timeout_minutes).detect_and_recover_stalled_jobs()


@router.post("/deploy/verify")
def verify_cloud_deployment_and_rollback(
    payload: DeployVerifyPayload,
    db: Session = Depends(get_db),
):
    """Verifica saúde pós-deploy, registra versão/commit e executa rollback automático caso falhe nos critérios críticos."""
    return CloudDeployRegistry(db).verify_post_deploy_and_rollback_if_unhealthy(
        version=payload.version or settings.APP_VERSION,
        commit_sha=payload.commit_sha,
        simulate_health_failure=payload.simulate_health_failure,
    )


@router.get("/deploy/state")
def get_cloud_deployment_state(db: Session = Depends(get_db)):
    """Retorna a versão publicada ativa, commit SHA e histórico recente de deploys/rollbacks."""
    return CloudDeployRegistry(db).get_state()


@router.post("/backup/verify-cycle")
def trigger_separate_cloud_backup_and_restore_test(
    keep_last: int = Query(default=settings.BACKUP_RETENTION_COUNT, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Executa backup em volume separado (/app/backups), aplica retenção e testa restauração em banco temporário."""
    return CloudAvailabilityMonitor(db).run_separate_cloud_backup_and_test_restore(keep_last=keep_last)
