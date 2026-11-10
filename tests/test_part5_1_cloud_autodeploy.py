"""Suíte de Testes Automatizados da Fase 5.1 — Cloud-First, Deploy Automático, Rollback, Eleição de Líder, Worker e Backup Separado."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.cloud_runtime import (
    CloudAvailabilityMonitor,
    CloudDeployRegistry,
    CloudTaskWorker,
    SchedulerLeaderLock,
)
from app.models.autonomous import PersistentOrchestratorQueue
from app.models.autopilot import AutopilotTaskRun, SystemAlert


def test_scheduler_leader_lock_prevents_duplicate_instances(db_session: Session):
    """Garante que apenas 1 instância do Scheduler adquira o lease por vez, impedindo tarefas duplicadas."""
    res1 = SchedulerLeaderLock.acquire_or_renew_leadership(
        db_session, candidate_id="cloud-scheduler-node-A", lease_seconds=120
    )
    assert res1["acquired"] is True
    assert res1["leader_id"] == "cloud-scheduler-node-A"

    # Segunda instância concorrente deve ser bloqueada enquanto o lease do node-A estiver ativo
    res2 = SchedulerLeaderLock.acquire_or_renew_leadership(
        db_session, candidate_id="cloud-scheduler-node-B", lease_seconds=120
    )
    assert res2["acquired"] is False
    assert res2["leader_id"] == "cloud-scheduler-node-A"

    # Renovação pelo próprio node-A continua permitida
    res_renew = SchedulerLeaderLock.acquire_or_renew_leadership(
        db_session, candidate_id="cloud-scheduler-node-A", lease_seconds=120
    )
    assert res_renew["acquired"] is True

    # Status de liderança deve refletir trava ativa
    status = SchedulerLeaderLock.get_leader_status(db_session)
    assert status["has_active_leader"] is True
    assert status["duplicate_scheduler_prevented"] is True


def test_cloud_task_worker_detects_and_recovers_stalled_jobs_with_exponential_backoff(db_session: Session):
    """Testa detecção de tarefas travadas (RUNNING além do timeout) e recuperação com backoff exponencial."""
    past_time = datetime.now(timezone.utc) - timedelta(minutes=45)

    # 1. Item na fila persistente travado em RUNNING há 45 minutos (tentativa 1 de 3)
    stalled_q = PersistentOrchestratorQueue(
        cycle_type="EVERY_6_HOURS",
        task_name="stalled_discovery_task",
        idempotency_key="stalled_discovery_task_key_1",
        status="RUNNING",
        attempt_count=1,
        max_attempts=3,
        locked_at=past_time,
        started_at=past_time,
    )
    # 2. Item na fila persistente que já atingiu max_attempts
    exhausted_q = PersistentOrchestratorQueue(
        cycle_type="EVERY_6_HOURS",
        task_name="exhausted_video_task",
        idempotency_key="exhausted_video_task_key_2",
        status="RUNNING",
        attempt_count=2,
        max_attempts=2,
        locked_at=past_time,
        started_at=past_time,
    )
    # 3. Execução do Autopilot travada em RUNNING
    stalled_exec = AutopilotTaskRun(
        task_name="autopilot_sync_stalled",
        idempotency_key="autopilot_sync_stalled_key_1",
        status="RUNNING",
        started_at=past_time,
    )
    db_session.add_all([stalled_q, exhausted_q, stalled_exec])
    db_session.commit()

    worker = CloudTaskWorker(db_session, task_timeout_minutes=20)
    recovery = worker.detect_and_recover_stalled_jobs()

    assert recovery["recovered_queue_jobs"] >= 1
    assert recovery["permanently_failed_queue_jobs"] >= 1
    assert recovery["recovered_task_executions"] >= 1

    db_session.refresh(stalled_q)
    db_session.refresh(exhausted_q)
    db_session.refresh(stalled_exec)

    assert stalled_q.status == "RECOVERED"
    assert stalled_q.attempt_count == 2
    assert stalled_q.scheduled_for is not None
    assert exhausted_q.status == "FAILED"
    assert stalled_exec.status == "RECOVERED_TIMEOUT"


def test_cloud_deploy_registry_post_deploy_verification_and_automatic_rollback(db_session: Session):
    """Testa registro de versão publicada e rollback automático caso a nova versão falhe nos critérios críticos de saúde."""
    registry = CloudDeployRegistry(db_session)

    # 1. Registra deploy saudável da versão 5.1.0
    healthy_deploy = registry.verify_post_deploy_and_rollback_if_unhealthy(
        version="5.1.0",
        commit_sha="abc1234healthy",
        simulate_health_failure=False,
    )
    assert healthy_deploy["healthy"] is True
    assert healthy_deploy["action"] == "DEPLOY_CONFIRMED"
    assert healthy_deploy["active_version"] == "5.1.0"
    assert healthy_deploy["active_commit_sha"] == "abc1234healthy"

    # 2. Simula deploy de versão 5.1.1 que falha nos critérios críticos de saúde -> deve acionar rollback automático para 5.1.0
    failed_deploy = registry.verify_post_deploy_and_rollback_if_unhealthy(
        version="5.1.1-broken",
        commit_sha="bad9999broken",
        simulate_health_failure=True,
    )
    assert failed_deploy["healthy"] is False
    assert failed_deploy["action"] == "ROLLED_BACK_AUTOMATICALLY"
    assert failed_deploy["rolled_back_to_version"] == "5.1.0"
    assert failed_deploy["rolled_back_to_commit_sha"] == "abc1234healthy"

    # Verifica que o estado ativo permaneceu na versão íntegra 5.1.0 e gerou alerta crítico
    state = registry.get_state()
    assert state["active_version"] == "5.1.0"
    assert state["active_commit_sha"] == "abc1234healthy"

    rollback_alert = (
        db_session.query(SystemAlert)
        .filter(SystemAlert.category == "CLOUD_DEPLOY_ROLLBACK")
        .first()
    )
    assert rollback_alert is not None
    assert rollback_alert.severity == "CRITICAL"


def test_cloud_availability_monitor_separate_backup_and_6_components_api(
    client: TestClient, db_session: Session, tmp_path: Path
):
    """Testa ciclo de backup em volume separado, teste de restauração e endpoints da Fase 5.1."""
    monitor = CloudAvailabilityMonitor(db_session)
    bkp_res = monitor.run_separate_cloud_backup_and_test_restore(keep_last=5)
    assert bkp_res["backup_verified"] is True
    assert bkp_res["restore_test_passed"] is True
    assert Path(bkp_res["backup_file"]).exists()

    # Verifica endpoint /health com metadados Cloud-First v5.1.0
    health_res = client.get("/health")
    assert health_res.status_code == 200
    h_data = health_res.json()
    assert h_data["status"] == "OK"
    assert h_data["version"] == "5.1.0"
    assert h_data["cloud_first"] is True
    assert h_data["depends_on_local_pc"] is False

    # Verifica endpoint /api/cloud/status com os 6 componentes separados da arquitetura de produção
    status_res = client.get("/api/cloud/status")
    assert status_res.status_code == 200
    st = status_res.json()
    assert st["cloud_first_operational"] is True
    assert st["depends_on_local_pc"] is False
    comps = st["components"]
    assert set(comps.keys()) == {
        "web_api",
        "scheduler",
        "worker",
        "database",
        "storage_and_backups",
        "monitoring",
    }
    assert comps["storage_and_backups"]["backups_separate_from_data"] is True

    # Verifica endpoints de deploy verify e backup verify-cycle via HTTP
    dep_res = client.post(
        "/api/cloud/deploy/verify",
        json={"version": "5.1.0", "commit_sha": "ci-cd-test-sha", "simulate_health_failure": False},
    )
    assert dep_res.status_code == 200
    assert dep_res.json()["action"] == "DEPLOY_CONFIRMED"
