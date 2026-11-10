"""Monitoramento Automático, Alertas, SMTP Opcional e Modo de Contingência (Seção 11)."""

from datetime import datetime, timezone
from email.message import EmailMessage
import os
import smtplib
from typing import Any, Dict, List
import psutil
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from app.config import settings
from app.core.logging import logger
from app.core.scheduler import union_scheduler
from app.models.affiliate import AffiliateLink
from app.models.autopilot import AutopilotTaskRun, EditorialQueueItem, EditorialState, SystemAlert
from app.models.marketplace import Marketplace


class SystemMonitor:
    """Monitora saúde da aplicação, banco, disco, memória, processos, links, filas e integrações."""

    DISK_MIN_FREE_PCT = 5.0
    RAM_MAX_USAGE_PCT = 92.0

    @classmethod
    def check_resources(cls) -> Dict[str, Any]:
        """Inspeciona disco, memória e processo atual para proteção de limite de recursos."""
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(str(settings.data_dir))
        proc = psutil.Process(os.getpid())
        proc_mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)

        ram_used_pct = float(vm.percent)
        disk_free_pct = round(100.0 - float(disk.percent), 2)
        contingency = (ram_used_pct >= cls.RAM_MAX_USAGE_PCT) or (disk_free_pct <= cls.DISK_MIN_FREE_PCT)

        return {
            "ram_used_pct": ram_used_pct,
            "ram_available_mb": round(vm.available / (1024 * 1024), 2),
            "disk_free_pct": disk_free_pct,
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "process_pid": proc.pid,
            "process_memory_mb": proc_mem_mb,
            "contingency_mode": contingency,
        }

    @classmethod
    def create_alert(
        cls,
        db: Session,
        severity: str,
        category: str,
        title: str,
        message: str,
        context: Dict[str, Any] | None = None,
    ) -> SystemAlert:
        """Registra um alerta no banco e envia notificação SMTP somente se autorizado pelo usuário."""
        alert = SystemAlert(
            severity=severity.upper(),
            category=category.upper(),
            title=title,
            message=message,
            is_resolved=False,
            notified_email=False,
            context=context or {},
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        if settings.SMTP_ENABLED and severity.upper() in ("WARNING", "CRITICAL"):
            sent = cls.send_optional_alert_email(title=f"[UNION MONEY AI] {title}", body=message)
            if sent:
                alert.notified_email = True
                db.commit()

        return alert

    @staticmethod
    def send_optional_alert_email(title: str, body: str) -> bool:
        """Envia e-mail via SMTP exclusivamente quando SMTP_ENABLED=True e credenciais configuradas."""
        if not settings.SMTP_ENABLED:
            return False
        if not (settings.SMTP_HOST.strip() and settings.SMTP_TO_EMAIL.strip()):
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = title
            msg["From"] = settings.SMTP_USER.strip() or "noreply@unionmoney.local"
            msg["To"] = settings.SMTP_TO_EMAIL.strip()
            msg.set_content(body)

            with smtplib.SMTP(settings.SMTP_HOST.strip(), settings.SMTP_PORT, timeout=10) as server:
                server.starttls()
                if settings.SMTP_USER.strip() and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER.strip(), settings.SMTP_PASSWORD)
                server.send_message(msg)
            return True
        except Exception as exc:
            logger.warning("Falha ao enviar alerta SMTP opcional: %s", exc)
            return False

    @classmethod
    def run_full_diagnostics(cls, db: Session) -> Dict[str, Any]:
        """Executa diagnóstico completo das 10 áreas exigidas na Seção 11."""
        resources = cls.check_resources()

        # 1. Banco de dados
        db_ok = False
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:
            cls.create_alert(db, "CRITICAL", "DATABASE", "Erro de conexão com banco", str(exc))

        # 2. Recursos (Disco e Memória)
        if resources["contingency_mode"]:
            cls.create_alert(
                db,
                "WARNING",
                "MEMORY" if resources["ram_used_pct"] >= cls.RAM_MAX_USAGE_PCT else "DISK",
                "Modo de Contingência de Recursos Ativado",
                f"RAM em {resources['ram_used_pct']}% | Disco livre em {resources['disk_free_pct']}%.",
                context=resources,
            )

        # 3. Links inválidos
        invalid_links = (
            db.query(func.count(AffiliateLink.id))
            .filter(AffiliateLink.validity_status != "VALID")
            .scalar()
            or 0
        )
        active_links = (
            db.query(func.count(AffiliateLink.id))
            .filter(AffiliateLink.is_active.is_(True))
            .scalar()
            or 0
        )

        # 4. Publicações e Fila Editorial
        failed_queue = (
            db.query(func.count(EditorialQueueItem.id))
            .filter(EditorialQueueItem.state == EditorialState.FALHOU)
            .scalar()
            or 0
        )
        published_queue = (
            db.query(func.count(EditorialQueueItem.id))
            .filter(EditorialQueueItem.state == EditorialState.PUBLICADO)
            .scalar()
            or 0
        )

        # 5. Integrações
        unavailable_mps = (
            db.query(func.count(Marketplace.id))
            .filter(Marketplace.availability_status == "UNAVAILABLE")
            .scalar()
            or 0
        )

        # 6. Erros de execução no Autopilot
        failed_tasks = (
            db.query(func.count(AutopilotTaskRun.id))
            .filter(AutopilotTaskRun.status == "FAILED")
            .scalar()
            or 0
        )

        # 7. Agendamentos
        scheduled_jobs = union_scheduler.list_jobs()

        # Alertas em aberto
        open_alerts: List[SystemAlert] = (
            db.query(SystemAlert)
            .filter(SystemAlert.is_resolved.is_(False))
            .order_by(SystemAlert.created_at.desc())
            .limit(20)
            .all()
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "application_status": "CONTINGENCY_MODE" if resources["contingency_mode"] else "HEALTHY",
            "database_healthy": db_ok,
            "resources": resources,
            "scheduler": {
                "enabled": settings.ENABLE_SCHEDULER,
                "registered_jobs_count": len(scheduled_jobs),
                "jobs": scheduled_jobs,
            },
            "links": {
                "active_links": active_links,
                "invalid_or_paused_links": invalid_links,
            },
            "publications": {
                "published_queue_items": published_queue,
                "failed_queue_items": failed_queue,
            },
            "integrations": {
                "unavailable_marketplaces": unavailable_mps,
            },
            "executions": {
                "failed_autopilot_runs": failed_tasks,
            },
            "open_alerts_count": len(open_alerts),
            "open_alerts": [
                {
                    "id": a.id,
                    "severity": a.severity,
                    "category": a.category,
                    "title": a.title,
                    "message": a.message,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in open_alerts
            ],
        }

