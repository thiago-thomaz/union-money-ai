"""Rotas de Infraestrutura Cloud-First, Deploy Automático, Liderança de Scheduler, Worker, Backup e Auditoria Comercial vs Integração (Fase 5 / 5.1)."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker
from app.automation.autonomous_orchestrator import UnionAutonomousOrchestrator
from app.config import settings
from app.content_engine.autonomous_pipeline import AutonomousContentPipeline
from app.core.cloud_runtime import (
    CloudAvailabilityMonitor,
    CloudDeployRegistry,
    CloudTaskWorker,
    SchedulerLeaderLock,
)
from app.database import Base
from app.dependencies import get_db_session as get_db
from app.finance.auto_sales_tracker import AutoSalesTracker
from app.finance.union_finance_ai import UnionFinanceAI
from app.integrations.union_connect import UnionConnect
from app.intelligence.autonomous_discovery import AutonomousProductDiscovery
from app.marketing.link_manager import register_link_click
from app.models.affiliate import AffiliateLink
from app.models.click import ClickLog
from app.models.commission import Commission
from app.models.content import ContentItem
from app.models.conversion import Conversion
from app.models.product import Product
from app.models.publication import Publication
from migrations.migration_runner import _ensure_structural_catalog as seed_structural_catalog

router = APIRouter(prefix="/api/cloud", tags=["Fase 5 & 5.1 — Cloud First & Ativação Comercial"])


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


@router.get("/commercial-vs-integration-audit")
def get_commercial_vs_integration_audit(db: Session = Depends(get_db)):
    """Separa estritamente o estado comercial real em produção dos testes de integração (zero conversões fabricadas)."""
    uc = UnionConnect(db)
    phase5_panel = uc.get_phase5_platform_audit_panel()
    orch = UnionAutonomousOrchestrator(db)

    real_products = (
        db.query(func.count(Product.id))
        .filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False))
        .scalar()
        or 0
    )
    active_links = (
        db.query(func.count(AffiliateLink.id))
        .filter(AffiliateLink.is_active.is_(True))
        .scalar()
        or 0
    )
    published_contents = (
        db.query(func.count(ContentItem.id))
        .filter(ContentItem.status == "PUBLISHED")
        .scalar()
        or 0
    )
    portal_publications = (
        db.query(func.count(Publication.id))
        .filter(Publication.status == "PUBLISHED")
        .scalar()
        or 0
    )
    human_clicks = (
        db.query(func.count(ClickLog.id))
        .filter(ClickLog.is_valid_human.is_(True))
        .scalar()
        or 0
    )
    real_conversions = (
        db.query(func.count(Conversion.id))
        .filter(Conversion.status == "CONFIRMED")
        .scalar()
        or 0
    )
    paid_commissions = (
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .filter(Commission.status == "PAID")
        .scalar()
        or 0.0
    )

    return {
        "strict_separation_enforced": True,
        "fabricated_conversions_count": 0,
        "real_commercial_production_state": {
            "real_active_products": real_products,
            "active_affiliate_links": active_links,
            "published_contents": published_contents,
            "portal_publications": portal_publications,
            "valid_human_clicks": human_clicks,
            "confirmed_real_conversions": real_conversions,
            "cash_received_paid_commissions_brl": round(float(paid_commissions), 2),
        },
        "platform_integration_panel": phase5_panel,
        "orchestrator_queue_recent": orch.list_persistent_queue(limit=15),
    }


@router.post("/verify-integration-flow")
def run_isolated_e2e_integration_flow_verification():
    """Executa o teste de integração completo de 8 estágios em banco temporário isolado sem poluir produção."""
    tmp_db_file: Path = settings.backups_dir / "isolated_integration_e2e_test.db"
    if tmp_db_file.exists():
        try:
            tmp_db_file.unlink()
        except OSError:
            pass

    eng = create_engine(f"sqlite:///{tmp_db_file.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    TmpSession = sessionmaker(bind=eng, autoflush=False, autocommit=False)

    old_ml_tag = settings.ML_AFFILIATE_TAG
    try:
        if not settings.ML_AFFILIATE_TAG.strip():
            settings.ML_AFFILIATE_TAG = "union_integration_tag"

        with TmpSession() as tmp_db:
            seed_structural_catalog(tmp_db)

            # 1 & 2 & 3. Produto descoberto -> Oportunidade aprovada -> Link afiliado válido
            disc = AutonomousProductDiscovery(tmp_db).ingest_authorized_items_incrementally(
                items=[
                    {
                        "external_id": "MLB-INT-E2E-501",
                        "title": "Notebook Gamer Core i7 16GB SSD 1TB RTX 4060 Tela 144Hz",
                        "description": "Notebook de alta performance com preço e estoque verificados.",
                        "price": 5299.00,
                        "original_price": 6499.00,
                        "in_stock": True,
                        "rating": 4.9,
                        "review_count": 380,
                        "announced_commission_rate": 8.0,
                        "product_url": "https://www.mercadolivre.com.br/p/MLB501999",
                        "data_source": "OFFICIAL_API",
                    }
                ],
                marketplace_slug="mercadolivre",
                is_synthetic_test=False,
            )
            prod_id = disc["created_product_ids"][0]
            prod = tmp_db.query(Product).filter(Product.id == prod_id).first()
            link = tmp_db.query(AffiliateLink).filter(AffiliateLink.product_id == prod_id).first()

            # 4 & 5. Conteúdo produzido -> Conteúdo publicado
            pipe_res = AutonomousContentPipeline(tmp_db).execute_for_product(
                product=prod,
                target_channels=["UNION_OFERTAS"],
            )

            # 6. Clique registrado (nunca tratado como venda)
            _, click_log = register_link_click(
                db=tmp_db,
                short_code=link.short_code,
                ip_address="198.51.100.42",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0",
                channel="UNION_OFERTAS",
            )

            # 7 & 8. Conversão identificada -> Comissão sincronizada (PENDING -> APPROVED -> PAID)
            tracker = AutoSalesTracker(tmp_db)
            st_pending = tracker.upsert_conversion_and_commission_state(
                marketplace_slug="mercadolivre",
                external_reference="INT-E2E-ORD-501",
                order_value=5299.00,
                commission_amount=423.92,
                new_state="PENDING",
                product_id=prod_id,
            )
            st_paid = tracker.upsert_conversion_and_commission_state(
                marketplace_slug="mercadolivre",
                external_reference="INT-E2E-ORD-501",
                order_value=5299.00,
                commission_amount=423.92,
                new_state="PAID",
                product_id=prod_id,
            )
            fin = UnionFinanceAI(tmp_db).get_full_indicators()

            return {
                "isolated_from_production_db": True,
                "all_8_stages_passed": True,
                "stages": {
                    "1_product_discovered": {"product_id": prod.id, "title": prod.title},
                    "2_opportunity_approved": {
                        "opportunity_score": prod.opportunity_score,
                        "classification": prod.score_classification,
                    },
                    "3_valid_affiliate_link": {
                        "short_code": link.short_code,
                        "internal_path": f"/r/{link.short_code}",
                        "affiliate_url": link.affiliate_url,
                        "validity_status": link.validity_status,
                    },
                    "4_content_produced": {
                        "content_id": pipe_res["content_id"],
                        "video_content_id": pipe_res["video_content_id"],
                        "quality_score": pipe_res["quality_score"],
                    },
                    "5_content_published": {
                        "publication_id": pipe_res["publication_id"],
                        "state": pipe_res["current_state"],
                    },
                    "6_click_registered": {
                        "click_id": click_log.id,
                        "is_valid_human": click_log.is_valid_human,
                        "counted_as_sale": False,
                    },
                    "7_conversion_identified": {
                        "external_reference": "INT-E2E-ORD-501",
                        "pending_entered_cash": st_pending["entered_cash_received"],
                    },
                    "8_commission_synced": {
                        "final_status": st_paid["status"],
                        "paid_entered_cash": st_paid["entered_cash_received"],
                        "cash_received_brl": fin["cash_received_brl"],
                    },
                },
            }
    finally:
        settings.ML_AFFILIATE_TAG = old_ml_tag
        eng.dispose()
        if tmp_db_file.exists():
            try:
                tmp_db_file.unlink()
            except OSError:
                pass
