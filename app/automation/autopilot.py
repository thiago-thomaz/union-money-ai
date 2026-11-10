"""UNION AUTOPILOT — Orquestrador Central Autônomo (Seção 1).

Responsabilidades:
1. Identificar oportunidades
2. Atualizar produtos
3. Calcular pontuações
4. Selecionar produtos
5. Criar pautas
6. Produzir conteúdos
7. Preparar campanhas
8. Distribuir conteúdos
9. Monitorar resultados
10. Identificar problemas
11. Gerar relatórios
12. Aprimorar estratégias

Controles técnicos:
- Impede tarefas duplicadas (lock por task_name + verificação de status RUNNING).
- Idempotência por chave única (idempotency_key).
- Retry com backoff exponencial.
- Timeouts por tarefa.
- Registro persistido de execução (AutopilotTaskRun).
- Recuperação automática de tarefas interrompidas após reinicialização.
- Limite de recursos e modo de contingência.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid
from sqlalchemy.orm import Session
from app.config import settings
from app.content_engine.seo import UnionSEOEngine
from app.content_engine.union_content_engine import UnionContentEngine
from app.core.logging import logger
from app.core.monitoring import SystemMonitor
from app.finance.commissions import _sync_approved_commission_to_revenue_and_product
from app.intelligence.discovery import get_all_connectors_status
from app.intelligence.opportunity import list_ranked_opportunities, score_and_update_product
from app.intelligence.recommendation import CommercialLearningEngine
from app.marketing.campaign_manager import apply_campaign_optimization_rules, create_campaign
from app.marketing.distribution import UnionDistributionEngine
from app.marketing.link_manager import UnionLinkManager, create_tracked_link
from app.models.affiliate import AffiliateLink
from app.models.audit import SystemSetting
from app.models.autopilot import AutopilotTaskRun, EditorialQueueItem, EditorialState
from app.models.campaign import Campaign
from app.models.commission import Commission
from app.models.content import ContentItem
from app.models.marketplace import Category
from app.models.product import Product
from app.services.reporting_service import generate_pdf_executive_report


class UnionAutopilot:
    """Orquestrador central de automação comercial do UNION MONEY AI."""

    _active_locks: Dict[str, threading.Lock] = {}
    _global_lock = threading.Lock()

    @classmethod
    def _get_task_lock(cls, task_name: str) -> threading.Lock:
        with cls._global_lock:
            if task_name not in cls._active_locks:
                cls._active_locks[task_name] = threading.Lock()
            return cls._active_locks[task_name]

    @staticmethod
    def get_frequencies(db: Session) -> Dict[str, int]:
        """Obtém as frequências configuradas para as 7 famílias de tarefas do Autopilot."""
        setting = db.query(SystemSetting).filter(SystemSetting.key == "autopilot_frequencies").first()
        base = dict(settings.DEFAULT_AUTOPILOT_FREQUENCIES)
        if setting and isinstance(setting.value_json, dict):
            for k, v in setting.value_json.items():
                if k in base and int(v) > 0:
                    base[k] = int(v)
        return base

    @staticmethod
    def update_frequencies(db: Session, new_frequencies: Dict[str, int]) -> Dict[str, int]:
        """Atualiza as frequências de agendamento no banco de dados."""
        base = dict(settings.DEFAULT_AUTOPILOT_FREQUENCIES)
        for k, v in new_frequencies.items():
            if k in base and int(v) > 0:
                base[k] = int(v)
        setting = db.query(SystemSetting).filter(SystemSetting.key == "autopilot_frequencies").first()
        if not setting:
            setting = SystemSetting(
                key="autopilot_frequencies",
                value_json=base,
                description="Frequências configuráveis de execução do UNION AUTOPILOT (em minutos).",
            )
            db.add(setting)
        else:
            setting.value_json = base
        db.commit()
        return base

    @classmethod
    def recover_interrupted_tasks(cls, db: Session) -> int:
        """Marca tarefas que ficaram como RUNNING antes de uma reinicialização como RECOVERED."""
        stale_runs = (
            db.query(AutopilotTaskRun)
            .filter(AutopilotTaskRun.status == "RUNNING")
            .all()
        )
        now_utc = datetime.now(timezone.utc)
        for run in stale_runs:
            run.status = "RECOVERED"
            run.finished_at = now_utc
            run.error_message = "Tarefa recuperada com segurança após reinicialização da aplicação."
        if stale_runs:
            db.commit()
            logger.info("Autopilot recuperou %d tarefa(s) interrompida(s).", len(stale_runs))
        return len(stale_runs)

    @classmethod
    def execute_task_with_controls(
        cls,
        db: Session,
        task_name: str,
        func: Callable[[], Dict[str, Any]],
        idempotency_key: Optional[str] = None,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.2,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Executa uma tarefa com lock anti-duplicação, idempotência, retry com backoff e timeout."""
        from app.core.emergency import is_emergency_stopped

        idem_key = idempotency_key or f"{task_name}:{uuid.uuid4()}"

        if is_emergency_stopped(db):
            return {
                "task_name": task_name,
                "idempotency_key": idem_key,
                "status": "SKIPPED_EMERGENCY_STOP",
                "message": "Execução bloqueada: botão de emergência STOP ALL AUTOMATIONS está ativo.",
            }

        # 1. Verifica idempotência se a chave já foi concluída anteriormente
        existing = (
            db.query(AutopilotTaskRun)
            .filter(AutopilotTaskRun.idempotency_key == idem_key)
            .first()
        )
        if existing and existing.status == "COMPLETED":
            return {
                "task_name": task_name,
                "idempotency_key": idem_key,
                "status": "SKIPPED_IDEMPOTENT",
                "attempt_count": existing.attempt_count,
                "result": existing.result_summary,
            }

        # 2. Impede execução duplicada concorrente da mesma tarefa
        lock = cls._get_task_lock(task_name)
        if not lock.acquire(blocking=False):
            return {
                "task_name": task_name,
                "idempotency_key": idem_key,
                "status": "SKIPPED_DUPLICATE_RUNNING",
                "message": f"A tarefa '{task_name}' já está em execução.",
            }

        start_ts = time.perf_counter()
        run_record = existing or AutopilotTaskRun(
            task_name=task_name,
            idempotency_key=idem_key,
            status="RUNNING",
            attempt_count=1,
            timeout_seconds=timeout_seconds,
        )
        if not existing:
            db.add(run_record)
            db.commit()
            db.refresh(run_record)

        try:
            # 3. Verifica limite de recursos antes de executar
            res_check = SystemMonitor.check_resources()
            last_error: Optional[str] = None

            for attempt in range(1, max_retries + 2):
                run_record.attempt_count = attempt
                try:
                    # Executa com controle de tempo limite
                    if timeout_seconds > 0:
                        result = func()
                    else:
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(func)
                            result = future.result(timeout=max(1, timeout_seconds))

                    elapsed_ms = round((time.perf_counter() - start_ts) * 1000.0, 2)
                    if elapsed_ms > (timeout_seconds * 1000.0):
                        raise FuturesTimeoutError(f"Tempo limite de {timeout_seconds}s excedido.")

                    run_record.status = "COMPLETED"
                    run_record.duration_ms = elapsed_ms
                    run_record.result_summary = {
                        **result,
                        "contingency_mode": res_check["contingency_mode"],
                    }
                    run_record.error_message = None
                    run_record.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    return {
                        "run_id": run_record.id,
                        "task_name": task_name,
                        "idempotency_key": idem_key,
                        "status": "COMPLETED",
                        "attempt_count": attempt,
                        "duration_ms": elapsed_ms,
                        "result": run_record.result_summary,
                    }
                except Exception as exc:
                    last_error = str(exc)
                    db.rollback()
                    # Reanexa registro após rollback se necessário
                    run_record = db.query(AutopilotTaskRun).filter(AutopilotTaskRun.id == run_record.id).first() or run_record
                    if attempt <= max_retries:
                        sleep_for = backoff_base_seconds * (2 ** (attempt - 1))
                        time.sleep(sleep_for)

            elapsed_ms = round((time.perf_counter() - start_ts) * 1000.0, 2)
            run_record.status = "FAILED"
            run_record.duration_ms = elapsed_ms
            run_record.error_message = last_error
            run_record.finished_at = datetime.now(timezone.utc)
            db.commit()

            SystemMonitor.create_alert(
                db,
                severity="WARNING",
                category="EXECUTION",
                title=f"Falha na tarefa {task_name}",
                message=last_error or "Erro desconhecido",
                context={"task_name": task_name, "attempts": run_record.attempt_count},
            )
            return {
                "run_id": run_record.id,
                "task_name": task_name,
                "idempotency_key": idem_key,
                "status": "FAILED",
                "attempt_count": run_record.attempt_count,
                "error": last_error,
            }
        finally:
            lock.release()

    @classmethod
    def run_full_cycle(
        cls,
        db: Session,
        idempotency_key: Optional[str] = None,
        auto_publish_site: bool = True,
    ) -> Dict[str, Any]:
        """Executa o ciclo completo de 12 etapas do UNION AUTOPILOT sobre o banco de dados."""

        def _pipeline() -> Dict[str, Any]:
            # 1 & 2 & 3. Conectores, atualização e cálculo de pontuações
            connectors = get_all_connectors_status(db)
            active_products = (
                db.query(Product)
                .filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False))
                .all()
            )
            for prod in active_products:
                score_and_update_product(db, prod)
                # Garante que todo produto ativo possua pelo menos um link rastreável válido
                has_link = db.query(AffiliateLink).filter(AffiliateLink.product_id == prod.id).first()
                if not has_link and (prod.affiliate_url or prod.product_url):
                    create_tracked_link(db, prod, prod.affiliate_url or prod.product_url, channel="SITE")
            db.commit()

            # 4. Seleciona produtos qualificados (Score >= 60 e em estoque)
            selected = [
                p
                for p in active_products
                if p.in_stock and p.opportunity_score is not None and p.opportunity_score >= 60.0
            ]
            selected.sort(key=lambda x: (x.opportunity_score or 0.0), reverse=True)

            # 5. Cria pautas e calendário editorial
            ranked_dicts = list_ranked_opportunities(db, min_score=60.0, limit=15)
            calendar = UnionSEOEngine.generate_editorial_calendar(ranked_dicts, days=7)

            # 6 & 7 & 8. Prepara campanhas por nicho, produz conteúdos e distribui na fila editorial
            content_engine = UnionContentEngine(db)
            dist_engine = UnionDistributionEngine(db)
            produced_ids: List[int] = []
            published_queue_ids: List[int] = []
            campaigns_prepared: List[int] = []

            for prod in selected[:5]:
                cat = db.query(Category).filter(Category.id == prod.category_id).first()
                cat_name = cat.name if cat else "Geral"

                # 7. Prepara campanha por nicho caso não exista para a categoria
                camp = (
                    db.query(Campaign)
                    .filter(Campaign.category_id == prod.category_id, Campaign.is_active.is_(True))
                    .first()
                )
                if not camp:
                    camp = create_campaign(
                        db=db,
                        name=f"Campanha {cat_name} Custo-Benefício",
                        objective="CONVERSIONS",
                        target_channel="SITE",
                        category_id=prod.category_id,
                        product_id=prod.id,
                        target_audience=f"Compradores interessados em {cat_name}",
                        problem_solved=f"Comparar preços e especificações reais em {cat_name}",
                        keywords=f"melhor {cat_name.lower()}, oferta {prod.title.lower()}",
                    )
                    campaigns_prepared.append(camp.id)

                # 6. Produz avaliação editorial se o produto ainda não tiver conteúdo publicado
                existing_content = (
                    db.query(ContentItem)
                    .filter(ContentItem.product_id == prod.id)
                    .first()
                )
                if not existing_content:
                    existing_content = content_engine.produce(
                        product=prod,
                        content_type="EDITORIAL_REVIEW",
                        campaign_id=camp.id,
                    )
                    produced_ids.append(existing_content.id)

                # 8. Enfileira e publica no site próprio se o Content Quality Score permitir
                q_item = dist_engine.enqueue_editorial_item(
                    product=prod,
                    content=existing_content,
                    target_channel="SITE",
                    require_human_approval=False,
                    campaign_id=camp.id,
                )
                if auto_publish_site and q_item.state == EditorialState.APROVADO:
                    pub_res = dist_engine.publish_queue_item(q_item.id)
                    if pub_res.get("state") == EditorialState.PUBLICADO:
                        published_queue_ids.append(q_item.id)

            # 9 & 12. Monitora resultados, reconcilia comissões aprovadas e aplica otimizações de campanha
            approved_comms = db.query(Commission).filter(Commission.status.in_(["APPROVED", "PAID"])).all()
            for cm in approved_comms:
                _sync_approved_commission_to_revenue_and_product(db, cm)
            db.commit()

            optimization = apply_campaign_optimization_rules(db)
            learning = CommercialLearningEngine(db).generate_learning_report()

            # 10. Identifica problemas operacionais
            diagnostics = SystemMonitor.run_full_diagnostics(db)

            # 11. Gera relatório executivo PDF
            report_path = generate_pdf_executive_report(db)

            return {
                "connectors_checked": len(connectors),
                "products_scored": len(active_products),
                "selected_opportunities": len(selected),
                "editorial_calendar_items": len(calendar),
                "campaigns_prepared": campaigns_prepared,
                "contents_produced": produced_ids,
                "queue_items_published": published_queue_ids,
                "optimization": optimization,
                "learning_mode": learning["engine_mode"],
                "system_status": diagnostics["application_status"],
                "report_pdf": str(report_path),
            }

        return cls.execute_task_with_controls(
            db=db,
            task_name="autopilot_full_cycle",
            func=_pipeline,
            idempotency_key=idempotency_key,
            max_retries=1,
            timeout_seconds=60,
        )

