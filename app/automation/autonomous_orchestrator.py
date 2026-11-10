"""UNION AUTONOMOUS ORCHESTRATOR — Orquestrador Autônomo 24/7 (Fase 4 - Seção 10).

Implementa ciclos configuráveis e fila persistente no banco de dados:
- A cada 6 horas (every_6_hours): Descoberta de produtos, Atualização de produtos, Validação de links, Verificação de integrações.
- Diariamente (daily): Seleção de oportunidades, Produção de conteúdos, Publicação autorizada, Análise de desempenho, Otimização editorial.
- Semanalmente (weekly): Análise de nichos, Revisão de campanhas, Identificação de oportunidades, Comparação de canais.
- Mensalmente (monthly): Conciliação financeira, Relatório de comissões, Análise de rentabilidade, Revisão de metas.

Controles obrigatórios:
- Fila persistente (PersistentOrchestratorQueue)
- Lock de execução
- Idempotência (idempotency_key)
- Retry com backoff exponencial
- Recuperação automática após queda
- Histórico auditável e proteção contra duplicidade
"""

from datetime import datetime, timedelta, timezone
import os
import socket
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.content_engine.autonomous_pipeline import AutonomousContentPipeline
from app.finance.auto_sales_tracker import AutoSalesTracker
from app.finance.union_finance_ai import UnionFinanceAI
from app.finance.wealth_simulator import UnionWealthSimulator
from app.integrations.union_connect import UnionConnect
from app.intelligence.autonomous_discovery import AutonomousProductDiscovery
from app.intelligence.opportunity import list_ranked_opportunities, score_and_update_product
from app.intelligence.union_growth_ai import UnionGrowthAI
from app.marketing.link_manager import UnionLinkManager
from app.models.audit import AuditLog
from app.models.autonomous import PersistentOrchestratorQueue
from app.models.product import Product


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UnionAutonomousOrchestrator:
    """Orquestrador Autônomo 24/7 com fila persistente, locks e recuperação após falha."""

    CYCLE_FREQUENCIES = {
        "every_6_hours": {
            "interval_hours": 6,
            "tasks": [
                "product_discovery",
                "product_update",
                "affiliate_link_validation",
                "integration_health_check",
            ],
        },
        "daily": {
            "interval_hours": 24,
            "tasks": [
                "opportunity_selection",
                "content_production",
                "authorized_publishing",
                "performance_analysis",
                "editorial_optimization",
            ],
        },
        "weekly": {
            "interval_hours": 168,
            "tasks": [
                "niche_analysis",
                "campaign_review",
                "opportunity_identification",
                "channel_comparison",
            ],
        },
        "monthly": {
            "interval_hours": 720,
            "tasks": [
                "financial_reconciliation",
                "commission_report",
                "profitability_analysis",
                "wealth_goal_review",
            ],
        },
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.worker_id = f"{socket.gethostname()}-pid-{os.getpid()}"

    def recover_persistent_queue(self) -> Dict[str, Any]:
        """Recupera tarefas presas em RUNNING após reinicialização ou queda inesperada."""
        if not settings.AUTO_RECOVERY:
            return {"status": "SKIPPED", "reason": "AUTO_RECOVERY=false"}

        stuck_jobs = (
            self.db.query(PersistentOrchestratorQueue)
            .filter(PersistentOrchestratorQueue.status == "RUNNING")
            .all()
        )
        recovered_count = 0
        for job in stuck_jobs:
            job.status = "RECOVERED"
            job.locked_by = None
            job.locked_at = None
            job.error_message = "Tarefa recuperada automaticamente após reinicialização do processo."
            job.scheduled_for = utc_now()
            recovered_count += 1

        if recovered_count > 0:
            self.db.add(
                AuditLog(
                    actor="UNION_AUTONOMOUS_ORCHESTRATOR",
                    action="QUEUE_RECOVERY",
                    entity_type="PersistentOrchestratorQueue",
                    entity_id="batch",
                    details={"recovered_jobs": recovered_count, "worker_id": self.worker_id},
                )
            )
            self.db.commit()

        return {
            "status": "OK",
            "recovered_jobs": recovered_count,
            "worker_id": self.worker_id,
        }

    def enqueue_or_execute_job(
        self,
        cycle_type: str,
        task_name: str,
        idempotency_key: str,
        fn: Callable[[], Dict[str, Any]],
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """Executa job na fila persistente com lock, idempotência e retry com backoff."""
        existing = (
            self.db.query(PersistentOrchestratorQueue)
            .filter(PersistentOrchestratorQueue.idempotency_key == idempotency_key)
            .first()
        )
        if existing and existing.status == "COMPLETED":
            return {
                "job_id": existing.id,
                "task_name": task_name,
                "status": "SKIPPED_DUPLICATE",
                "idempotency_key": idempotency_key,
                "result": existing.result_json,
            }

        if existing and existing.status == "RUNNING":
            return {
                "job_id": existing.id,
                "task_name": task_name,
                "status": "LOCKED_ALREADY_RUNNING",
                "locked_by": existing.locked_by,
            }

        if not existing:
            job = PersistentOrchestratorQueue(
                cycle_type=cycle_type.upper(),
                task_name=task_name,
                idempotency_key=idempotency_key,
                status="QUEUED",
                attempt_count=0,
                max_attempts=max_attempts,
                payload_json={"worker_id": self.worker_id},
            )
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
        else:
            job = existing

        # Acquire lock
        job.status = "RUNNING"
        job.locked_by = self.worker_id
        job.locked_at = utc_now()
        job.started_at = utc_now()
        self.db.commit()

        last_exc: Optional[str] = None
        while job.attempt_count < job.max_attempts:
            job.attempt_count += 1
            self.db.commit()
            try:
                result = fn()
                job.status = "COMPLETED"
                job.result_json = result
                job.finished_at = utc_now()
                job.locked_by = None
                job.error_message = None
                self.db.commit()
                return {
                    "job_id": job.id,
                    "task_name": task_name,
                    "status": "COMPLETED",
                    "attempts": job.attempt_count,
                    "result": result,
                }
            except Exception as exc:
                last_exc = str(exc)
                backoff_seconds = 2 ** job.attempt_count
                job.error_message = last_exc
                job.scheduled_for = utc_now() + timedelta(seconds=backoff_seconds)
                self.db.commit()

        job.status = "FAILED"
        job.locked_by = None
        job.finished_at = utc_now()
        self.db.commit()
        return {
            "job_id": job.id,
            "task_name": task_name,
            "status": "FAILED",
            "attempts": job.attempt_count,
            "error": last_exc,
        }

    def execute_cycle(
        self, cycle_type: str, bucket_suffix: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executa qualquer um dos 4 ciclos oficiais (every_6_hours, daily, weekly, monthly)."""
        if cycle_type not in self.CYCLE_FREQUENCIES:
            raise ValueError(f"Ciclo inválido: {cycle_type}")

        bucket = bucket_suffix or utc_now().strftime("%Y-%m-%d-%H")
        results: Dict[str, Any] = {}

        if cycle_type == "every_6_hours":
            discovery_svc = AutonomousProductDiscovery(self.db)
            connect_svc = UnionConnect(self.db)

            results["product_discovery"] = self.enqueue_or_execute_job(
                cycle_type="every_6_hours",
                task_name="product_discovery",
                idempotency_key=f"6h:discovery:{bucket}",
                fn=lambda: discovery_svc.run_continuous_discovery_cycle(limit_per_query=2),
            )
            results["product_update"] = self.enqueue_or_execute_job(
                cycle_type="every_6_hours",
                task_name="product_update",
                idempotency_key=f"6h:product_update:{bucket}",
                fn=lambda: discovery_svc.suspend_invalid_or_uninteresting_products(),
            )
            results["affiliate_link_validation"] = self.enqueue_or_execute_job(
                cycle_type="every_6_hours",
                task_name="affiliate_link_validation",
                idempotency_key=f"6h:link_validation:{bucket}",
                fn=lambda: UnionLinkManager.review_all_links(self.db),
            )
            results["integration_health_check"] = self.enqueue_or_execute_job(
                cycle_type="every_6_hours",
                task_name="integration_health_check",
                idempotency_key=f"6h:integrations:{bucket}",
                fn=lambda: {"connectors": connect_svc.list_all_connectors()},
            )

        elif cycle_type == "daily":
            pipeline_svc = AutonomousContentPipeline(self.db)
            growth_ai = UnionGrowthAI(self.db)

            def _select_and_produce() -> Dict[str, Any]:
                active_prods = self.db.query(Product).filter(Product.is_active.is_(True)).all()
                for p in active_prods:
                    score_and_update_product(self.db, p)
                self.db.commit()

                top_products = (
                    self.db.query(Product)
                    .filter(Product.is_active.is_(True))
                    .order_by(Product.opportunity_score.desc().nullslast())
                    .limit(2)
                    .all()
                )
                produced = []
                for prod in top_products:
                    produced.append(
                        pipeline_svc.execute_for_product(
                            product=prod,
                            target_channels=["UNION_OFERTAS", "YOUTUBE_SHORTS"],
                        )
                    )
                return {
                    "recalculated_products": len(active_prods),
                    "pipelines_executed": len(produced),
                    "pipelines": produced,
                }

            results["opportunity_content_and_publish"] = self.enqueue_or_execute_job(
                cycle_type="daily",
                task_name="opportunity_content_and_publish",
                idempotency_key=f"daily:pipeline:{bucket}",
                fn=_select_and_produce,
            )
            results["performance_analysis"] = self.enqueue_or_execute_job(
                cycle_type="daily",
                task_name="performance_analysis",
                idempotency_key=f"daily:performance:{bucket}",
                fn=lambda: growth_ai.evaluate_commercial_performance(),
            )
            results["editorial_optimization"] = self.enqueue_or_execute_job(
                cycle_type="daily",
                task_name="editorial_optimization",
                idempotency_key=f"daily:editorial_refresh:{bucket}",
                fn=lambda: pipeline_svc.refresh_outdated_contents(),
            )

        elif cycle_type == "weekly":
            growth_ai = UnionGrowthAI(self.db)
            sales_tracker = AutoSalesTracker(self.db)

            results["niche_and_campaign_optimization"] = self.enqueue_or_execute_job(
                cycle_type="weekly",
                task_name="niche_and_campaign_optimization",
                idempotency_key=f"weekly:growth_opt:{bucket}",
                fn=lambda: growth_ai.update_priorities_automatically(),
            )
            results["commission_sync"] = self.enqueue_or_execute_job(
                cycle_type="weekly",
                task_name="commission_sync",
                idempotency_key=f"weekly:comm_sync:{bucket}",
                fn=lambda: sales_tracker.sync_from_official_apis(),
            )
            results["opportunity_ranking"] = self.enqueue_or_execute_job(
                cycle_type="weekly",
                task_name="opportunity_ranking",
                idempotency_key=f"weekly:opp_rank:{bucket}",
                fn=lambda: {"opportunities": list_ranked_opportunities(self.db, limit=10)},
            )

        elif cycle_type == "monthly":
            finance_ai = UnionFinanceAI(self.db)
            simulator = UnionWealthSimulator(self.db)

            results["financial_reconciliation"] = self.enqueue_or_execute_job(
                cycle_type="monthly",
                task_name="financial_reconciliation",
                idempotency_key=f"monthly:reconcile:{bucket}",
                fn=lambda: finance_ai.reconcile_commissions(),
            )
            results["financial_report_and_profitability"] = self.enqueue_or_execute_job(
                cycle_type="monthly",
                task_name="financial_report_and_profitability",
                idempotency_key=f"monthly:report:{bucket}",
                fn=lambda: finance_ai.get_full_indicators(),
            )
            results["wealth_goal_review"] = self.enqueue_or_execute_job(
                cycle_type="monthly",
                task_name="wealth_goal_review",
                idempotency_key=f"monthly:wealth:{bucket}",
                fn=lambda: simulator.simulate("MODERADO"),
            )

        return {
            "cycle_type": cycle_type,
            "executed_at": utc_now().isoformat(),
            "worker_id": self.worker_id,
            "jobs": results,
        }

    def list_persistent_queue(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lista o histórico auditável da fila persistente do orquestrador."""
        rows = (
            self.db.query(PersistentOrchestratorQueue)
            .order_by(PersistentOrchestratorQueue.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "job_uid": r.job_uid,
                "cycle_type": r.cycle_type,
                "task_name": r.task_name,
                "idempotency_key": r.idempotency_key,
                "status": r.status,
                "attempt_count": r.attempt_count,
                "max_attempts": r.max_attempts,
                "locked_by": r.locked_by,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in rows
        ]
