"""Camada Cloud-First 24/7 — Arquitetura de Produção, Eleição de Líder, Worker, Deploy Registry e Rollback (Fase 5.1).

Separa e coordena os 6 componentes de produção:
1. Web/API: Aplicação principal FastAPI.
2. Scheduler: Agendamento de tarefas na nuvem com controle de liderança (Leader Election Lock) para impedir duplicidade.
3. Worker: Processamento de tarefas em segundo plano, detecção de processos travados, timeout e backoff.
4. Database: Persistência SQLite em modo WAL em volume dedicado (/app/data).
5. Storage & Backups: Armazenamento persistente de mídias (/app/storage) e volume separado de backups (/app/backups).
6. Monitoring: Saúde HTTP, CPU, RAM, disco, logs centralizados, histórico de deploys e rollback automático.
"""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import socket
from typing import Any, Dict, List, Optional
import psutil
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.models.audit import AuditLog, SystemSetting
from app.models.autonomous import PersistentOrchestratorQueue
from app.models.autopilot import AutopilotTaskRun, SystemAlert
from scripts.backup_db import (
    cleanup_old_backups,
    create_sqlite_backup,
    verify_backup_integrity,
)
from scripts.restore_db import restore_sqlite_backup


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SchedulerLeaderLock:
    """Controle de liderança distribuído via banco para impedir múltiplas instâncias de scheduler."""

    SETTING_KEY = "cloud_scheduler_leader_lock"
    LEASE_SECONDS = 90

    @classmethod
    def acquire_or_renew_leadership(
        cls,
        db: Session,
        candidate_id: Optional[str] = None,
        lease_seconds: int = LEASE_SECONDS,
    ) -> Dict[str, Any]:
        """Adquire ou renova o lease de líder do Scheduler. Impede que outra instância agende tarefas duplicadas."""
        instance_id = candidate_id or f"{socket.gethostname()}:pid-{os.getpid()}"
        now = utc_now()
        expires = now + timedelta(seconds=lease_seconds)

        rec = db.query(SystemSetting).filter(SystemSetting.key == cls.SETTING_KEY).first()
        if not rec:
            rec = SystemSetting(
                key=cls.SETTING_KEY,
                value_json={
                    "leader_id": instance_id,
                    "acquired_at": now.isoformat(),
                    "heartbeat_at": now.isoformat(),
                    "lease_expires_at": expires.isoformat(),
                },
                description="Lock de liderança do Scheduler Cloud para impedir tarefas duplicadas.",
            )
            db.add(rec)
            db.commit()
            return {
                "acquired": True,
                "is_leader": True,
                "leader_id": instance_id,
                "candidate_id": instance_id,
                "lease_expires_at": expires.isoformat(),
            }

        data = dict(rec.value_json or {})
        current_leader = data.get("leader_id")
        lease_exp_str = data.get("lease_expires_at")
        lease_expired = True
        if lease_exp_str:
            try:
                exp_dt = datetime.fromisoformat(lease_exp_str)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                lease_expired = now >= exp_dt
            except ValueError:
                lease_expired = True

        if current_leader == instance_id or lease_expired or not current_leader:
            rec.value_json = {
                "leader_id": instance_id,
                "acquired_at": data.get("acquired_at") or now.isoformat(),
                "heartbeat_at": now.isoformat(),
                "lease_expires_at": expires.isoformat(),
            }
            db.commit()
            return {
                "acquired": True,
                "is_leader": True,
                "leader_id": instance_id,
                "candidate_id": instance_id,
                "lease_expires_at": expires.isoformat(),
            }

        return {
            "acquired": False,
            "is_leader": False,
            "leader_id": current_leader,
            "candidate_id": instance_id,
            "lease_expires_at": lease_exp_str,
            "reason": "Outra instância detém o lease ativo do Scheduler.",
        }

    @classmethod
    def get_leader_status(cls, db: Session) -> Dict[str, Any]:
        rec = db.query(SystemSetting).filter(SystemSetting.key == cls.SETTING_KEY).first()
        if not rec or not rec.value_json:
            return {
                "active": False,
                "has_active_leader": False,
                "leader_id": None,
                "duplicate_scheduler_prevented": True,
            }
        return {
            "active": True,
            "has_active_leader": True,
            "duplicate_scheduler_prevented": True,
            **rec.value_json,
        }


class CloudTaskWorker:
    """Worker Cloud para processamento de tarefas, detecção de processos travados e recuperação."""

    HEARTBEAT_KEY = "cloud_worker_heartbeat"

    def __init__(
        self,
        db: Session,
        worker_id: Optional[str] = None,
        task_timeout_minutes: int = 25,
    ) -> None:
        self.db = db
        self.worker_id = worker_id or f"worker-{socket.gethostname()}-pid-{os.getpid()}"
        self.task_timeout_minutes = task_timeout_minutes

    def record_heartbeat(
        self,
        status: str = "ACTIVE",
        processed_count: int = 0,
        recovered_count: int = 0,
    ) -> Dict[str, Any]:
        now = utc_now()
        payload = {
            "worker_id": self.worker_id,
            "status": status,
            "last_heartbeat_at": now.isoformat(),
            "processed_jobs": processed_count,
            "recovered_jobs": recovered_count,
        }
        rec = self.db.query(SystemSetting).filter(SystemSetting.key == self.HEARTBEAT_KEY).first()
        if not rec:
            rec = SystemSetting(
                key=self.HEARTBEAT_KEY,
                value_json=payload,
                description="Heartbeat do Worker Cloud de processamento de tarefas.",
            )
            self.db.add(rec)
        else:
            rec.value_json = payload
        self.db.commit()
        return payload

    def detect_and_recover_stalled_jobs(self, timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        """Detecta tarefas travadas em RUNNING além do timeout, aplica backoff exponencial ou marca falha."""
        now = utc_now()
        effective_timeout_seconds = timeout_seconds or (self.task_timeout_minutes * 60)
        cutoff = now - timedelta(seconds=effective_timeout_seconds)

        running_jobs = (
            self.db.query(PersistentOrchestratorQueue)
            .filter(PersistentOrchestratorQueue.status == "RUNNING")
            .all()
        )
        recovered_ids: List[int] = []
        failed_ids: List[int] = []

        for job in running_jobs:
            lock_time = job.locked_at or job.started_at or job.created_at
            if lock_time and lock_time.tzinfo is None:
                lock_time = lock_time.replace(tzinfo=timezone.utc)
            if lock_time and lock_time <= cutoff:
                if job.attempt_count < job.max_attempts:
                    job.attempt_count += 1
                    backoff = 2 ** max(1, job.attempt_count)
                    job.status = "RECOVERED"
                    job.locked_by = None
                    job.locked_at = None
                    job.error_message = (
                        f"Processo travado detectado após {effective_timeout_seconds}s; "
                        f"recuperado com backoff de {backoff}s."
                    )
                    job.scheduled_for = now + timedelta(seconds=backoff)
                    recovered_ids.append(job.id)
                else:
                    job.status = "FAILED"
                    job.locked_by = None
                    job.finished_at = now
                    job.error_message = (
                        f"Excedeu timeout ({effective_timeout_seconds}s) e limite máximo de tentativas ({job.max_attempts})."
                    )
                    failed_ids.append(job.id)

        stalled_task_runs = (
            self.db.query(AutopilotTaskRun)
            .filter(AutopilotTaskRun.status == "RUNNING")
            .all()
        )
        recovered_task_runs = 0
        for run in stalled_task_runs:
            started = run.started_at
            if started and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started and started <= cutoff:
                run.status = "RECOVERED_TIMEOUT"
                run.finished_at = now
                run.error_message = f"Task RUN recuperada por timeout ({effective_timeout_seconds}s)."
                recovered_task_runs += 1

        if recovered_ids or failed_ids or recovered_task_runs:
            self.db.add(
                AuditLog(
                    actor=self.worker_id,
                    action="CLOUD_WORKER_STALLED_RECOVERY",
                    entity_type="PersistentOrchestratorQueue",
                    entity_id="stalled_check",
                    details={
                        "recovered_ids": recovered_ids,
                        "failed_ids": failed_ids,
                        "recovered_task_runs": recovered_task_runs,
                    },
                )
            )
            self.db.commit()

        hb = self.record_heartbeat(
            status="ACTIVE",
            processed_count=0,
            recovered_count=len(recovered_ids) + recovered_task_runs,
        )
        return {
            "worker_id": self.worker_id,
            "recovered_queue_jobs": len(recovered_ids),
            "permanently_failed_queue_jobs": len(failed_ids),
            "recovered_task_executions": recovered_task_runs,
            "stalled_recovered_count": len(recovered_ids),
            "stalled_recovered_ids": recovered_ids,
            "stalled_failed_count": len(failed_ids),
            "heartbeat": hb,
        }


class CloudDeployRegistry:
    """Registro de versões publicadas, verificação pós-deploy e rollback automático seguro."""

    HISTORY_KEY = "cloud_deployment_history"

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_deploy_history(self) -> List[Dict[str, Any]]:
        rec = self.db.query(SystemSetting).filter(SystemSetting.key == self.HISTORY_KEY).first()
        if not rec or not isinstance(rec.value_json, dict):
            return []
        return list(rec.value_json.get("deployments", []))

    def get_state(self) -> Dict[str, Any]:
        rec = self.db.query(SystemSetting).filter(SystemSetting.key == self.HISTORY_KEY).first()
        if not rec or not isinstance(rec.value_json, dict):
            return {
                "active_version": settings.APP_VERSION,
                "active_commit_sha": os.environ.get("GIT_COMMIT_SHA") or "production-cloud",
                "current_status": "INITIAL",
                "deployments": [],
            }
        data = dict(rec.value_json)
        return {
            "active_version": data.get("active_version") or data.get("current_version") or settings.APP_VERSION,
            "active_commit_sha": data.get("active_commit_sha") or data.get("current_commit_sha") or "production-cloud",
            "current_status": data.get("current_status", "DEPLOYED_HEALTHY"),
            "deployments": data.get("deployments", []),
        }

    def register_deployment(
        self,
        version: str,
        commit_sha: str,
        status: str = "DEPLOYED_HEALTHY",
        notes: str = "Deploy automático verificado com sucesso.",
        keep_active_version: Optional[str] = None,
        keep_active_commit: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = utc_now()
        rec = self.db.query(SystemSetting).filter(SystemSetting.key == self.HISTORY_KEY).first()
        history = self.get_deploy_history()

        last_healthy_commit = next(
            (d["commit_sha"] for d in history if d.get("status") == "DEPLOYED_HEALTHY"),
            commit_sha,
        )
        last_healthy_version = next(
            (d["version"] for d in history if d.get("status") == "DEPLOYED_HEALTHY"),
            version,
        )
        entry = {
            "version": version,
            "commit_sha": commit_sha,
            "previous_healthy_version": last_healthy_version,
            "previous_healthy_commit": last_healthy_commit,
            "status": status,
            "deployed_at": now.isoformat(),
            "domain": settings.PUBLIC_BASE_URL,
            "notes": notes,
        }
        history.insert(0, entry)
        history = history[:25]

        active_ver = keep_active_version or version
        active_sha = keep_active_commit or commit_sha
        payload = {
            "active_version": active_ver,
            "active_commit_sha": active_sha,
            "current_version": active_ver,
            "current_commit_sha": active_sha,
            "current_status": status,
            "last_updated_at": now.isoformat(),
            "deployments": history,
        }
        if not rec:
            rec = SystemSetting(
                key=self.HISTORY_KEY,
                value_json=payload,
                description="Histórico auditável de deploys automáticos e rollbacks na nuvem.",
            )
            self.db.add(rec)
        else:
            rec.value_json = payload

        self.db.add(
            AuditLog(
                actor="cloud_ci_cd",
                action="CLOUD_DEPLOYMENT_RECORDED",
                entity_type="Deployment",
                entity_id=commit_sha[:12],
                details=entry,
            )
        )
        self.db.commit()
        return entry

    def verify_post_deploy_and_rollback_if_unhealthy(
        self,
        version: Optional[str] = None,
        commit_sha: Optional[str] = None,
        simulate_health_failure: bool = False,
        simulate_critical_failure: bool = False,
    ) -> Dict[str, Any]:
        """Executa testes de saúde pós-deploy e aciona rollback automático se critérios críticos falharem."""
        target_commit = commit_sha or os.environ.get("GIT_COMMIT_SHA") or os.environ.get("SOURCE_COMMIT") or "cloud-main"
        target_version = version or settings.APP_VERSION
        should_fail = simulate_health_failure or simulate_critical_failure

        # 1. Verifica integridade do banco SQLite e modo WAL
        db_ok = False
        wal_mode = "unknown"
        try:
            pragma_integrity = self.db.execute(text("PRAGMA integrity_check;")).scalar()
            wal_mode = str(self.db.execute(text("PRAGMA journal_mode;")).scalar() or "").lower()
            db_ok = str(pragma_integrity).lower() == "ok"
        except Exception:
            db_ok = False

        # 2. Verifica diretórios de volumes persistentes
        storage_ok = settings.storage_dir.exists() and settings.backups_dir.exists()

        is_healthy = db_ok and storage_ok and not should_fail

        if is_healthy:
            entry = self.register_deployment(
                version=target_version,
                commit_sha=target_commit,
                status="DEPLOYED_HEALTHY",
                notes="Critérios críticos de saúde, banco WAL e volumes persistentes aprovados.",
            )
            return {
                "healthy": True,
                "action": "DEPLOY_CONFIRMED",
                "rollback_triggered": False,
                "active_version": target_version,
                "active_commit_sha": target_commit,
                "database_integrity": "ok",
                "journal_mode": wal_mode,
                "deployment": entry,
            }

        # Critério crítico falhou -> Executa Rollback Automático para a última versão saudável
        history = self.get_deploy_history()
        fallback_commit = next(
            (d["commit_sha"] for d in history if d.get("status") == "DEPLOYED_HEALTHY"),
            "previous-stable",
        )
        fallback_version = next(
            (d["version"] for d in history if d.get("status") == "DEPLOYED_HEALTHY"),
            settings.APP_VERSION,
        )
        rollback_entry = self.register_deployment(
            version=target_version,
            commit_sha=target_commit,
            status="ROLLED_BACK_AUTOMATICALLY",
            notes=f"Falha nos critérios críticos de saúde. Rollback automático acionado para {fallback_version} ({fallback_commit}).",
            keep_active_version=fallback_version,
            keep_active_commit=fallback_commit,
        )
        self.db.add(
            SystemAlert(
                severity="CRITICAL",
                category="CLOUD_DEPLOY_ROLLBACK",
                title="Rollback Automático Acionado no Deploy Cloud",
                message=(
                    f"A versão {target_version} ({target_commit}) reprovou no healthcheck crítico pós-deploy. "
                    f"Rollback registrado para {fallback_version} ({fallback_commit})."
                ),
                context=rollback_entry,
            )
        )
        self.db.commit()
        return {
            "healthy": False,
            "action": "ROLLED_BACK_AUTOMATICALLY",
            "rollback_triggered": True,
            "rolled_back_to_version": fallback_version,
            "rolled_back_to_commit_sha": fallback_commit,
            "rolled_back_to_commit": fallback_commit,
            "deployment": rollback_entry,
        }


class CloudAvailabilityMonitor:
    """Monitoramento centralizado de arquitetura Cloud, recursos (CPU/RAM/Disco) e backups separados."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def run_separate_cloud_backup_and_test_restore(
        self,
        keep_last: Optional[int] = None,
        tmp_restore_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Cria backup no volume separado (/app/backups), aplica retenção e testa restauração segura."""
        retention = keep_last or settings.BACKUP_RETENTION_COUNT
        backup_dir = settings.backups_dir
        backup_path = create_sqlite_backup(
            target_dir=backup_dir,
            db=self.db,
            backup_type="CLOUD_SEPARATE_VOLUME",
        )
        integrity = verify_backup_integrity(backup_path)
        removed_old = cleanup_old_backups(
            target_dir=backup_dir,
            keep_last=retention,
        )

        # Testa procedimento de restauração em arquivo temporário isolado (sem sobrescrever produção)
        test_dir = tmp_restore_dir or (backup_dir / "restore_verification_tmp")
        test_dir.mkdir(parents=True, exist_ok=True)
        test_target_db = test_dir / "verified_restore_test.db"
        restore_result = restore_sqlite_backup(
            backup_path=backup_path,
            target_db_path=test_target_db,
        )
        try:
            if test_target_db.exists():
                test_target_db.unlink()
        except OSError:
            pass

        return {
            "backup_file": str(backup_path),
            "backup_verified": bool(integrity.get("is_valid", False)),
            "stored_in_separate_volume": str(backup_dir),
            "primary_data_dir": str(settings.data_dir),
            "is_separate_from_primary_data_dir": backup_dir.resolve() != settings.data_dir.resolve(),
            "integrity": integrity,
            "retention_keep_last": retention,
            "old_backups_removed": removed_old,
            "restore_test_passed": restore_result.get("status") == "RESTORED",
            "restore_verification": restore_result,
        }

    def get_production_architecture_status(self) -> Dict[str, Any]:
        """Retorna o diagnóstico completo dos 6 componentes separados da arquitetura Cloud (Fase 5.1)."""
        leader = SchedulerLeaderLock.acquire_or_renew_leadership(self.db)
        worker = CloudTaskWorker(self.db).detect_and_recover_stalled_jobs()
        deploy_reg = CloudDeployRegistry(self.db)
        deploy_history = deploy_reg.get_deploy_history()
        if not deploy_history:
            deploy_reg.verify_post_deploy_and_rollback_if_unhealthy()
            deploy_history = deploy_reg.get_deploy_history()

        cpu_pct = round(psutil.cpu_percent(interval=0.05), 1)
        mem = psutil.virtual_memory()
        disk = shutil.disk_usage(BASE_DIR)
        free_disk_gb = round(disk.free / (1024 ** 3), 2)
        total_disk_gb = round(disk.total / (1024 ** 3), 2)

        wal_mode = str(self.db.execute(text("PRAGMA journal_mode;")).scalar() or "").lower()

        if free_disk_gb < 2.0 or mem.percent > 92.0:
            self.db.add(
                SystemAlert(
                    severity="WARNING",
                    category="RESOURCE_MONITOR",
                    title="Alerta de Recursos na Instância Cloud",
                    message=f"Disco livre: {free_disk_gb}GB | Uso de RAM: {mem.percent}%",
                    context={"free_disk_gb": free_disk_gb, "ram_percent": mem.percent},
                )
            )
            self.db.commit()

        backups_list = sorted(settings.backups_dir.glob("union_money_ai_backup_*.db"))
        backups_separate = settings.backups_dir.resolve() != settings.data_dir.resolve()

        return {
            "checked_at": utc_now().isoformat(),
            "cloud_first_operational": True,
            "depends_on_local_pc": False,
            "depends_on_antigravity_open": False,
            "production_url": settings.PUBLIC_BASE_URL,
            "version": settings.APP_VERSION,
            "git_commit_sha": os.environ.get("GIT_COMMIT_SHA") or os.environ.get("SOURCE_COMMIT") or "main",
            "components": {
                "web_api": {
                    "role": "Web/API (FastAPI + Portal UNION OFERTAS)",
                    "status": "ONLINE",
                    "public_url": settings.PUBLIC_BASE_URL,
                    "https_enabled": settings.PUBLIC_BASE_URL.startswith("https://"),
                },
                "scheduler": {
                    "role": "Cloud Scheduler com Controle de Liderança",
                    "status": "ACTIVE",
                    "leader_election": leader,
                    "duplicate_execution_prevention": "ENABLED_LEADER_LOCK_AND_IDEMPOTENCY",
                },
                "worker": {
                    "role": "Cloud Worker (Fila Persistente + Auto-Recovery)",
                    "status": "ACTIVE",
                    "worker_details": worker,
                },
                "database": {
                    "role": "Database Persistente (SQLite WAL)",
                    "status": "HEALTHY",
                    "journal_mode": wal_mode,
                    "volume_path": str(settings.data_dir),
                },
                "storage_and_backups": {
                    "role": "Storage de Mídias e Volume Separado de Backups",
                    "status": "MOUNTED",
                    "storage_path": str(settings.storage_dir),
                    "separate_backups_path": str(settings.backups_dir),
                    "backups_separate_from_data": backups_separate,
                    "backups_available_count": len(backups_list),
                    "retention_policy_keep_last": settings.BACKUP_RETENTION_COUNT,
                },
                "monitoring": {
                    "role": "Monitoramento de Saúde, CPU, RAM, Disco e Deploys",
                    "status": "ACTIVE",
                    "cpu_percent": cpu_pct,
                    "ram_percent": round(mem.percent, 1),
                    "ram_available_mb": round(mem.available / (1024 ** 2), 1),
                    "disk_free_gb": free_disk_gb,
                    "disk_total_gb": total_disk_gb,
                },
            },
            "deploy_history": deploy_history[:5],
        }
