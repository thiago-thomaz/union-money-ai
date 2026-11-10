"""Rotas de API e Painel para o UNION AUTOPILOT, Fila Editorial, Gestor de Links, SEO, Vídeo e Monitoramento."""

from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.automation.autopilot import UnionAutopilot
from app.content_engine.ai_providers import ai_provider_router
from app.content_engine.seo import UnionSEOEngine
from app.content_engine.video import UnionVideoEngine
from app.core.monitoring import SystemMonitor
from app.dependencies import get_db_session
from app.intelligence.opportunity import list_ranked_opportunities
from app.marketing.campaign_manager import apply_campaign_optimization_rules
from app.marketing.distribution import UnionDistributionEngine
from app.marketing.link_manager import UnionLinkManager
from app.models.autopilot import AutopilotTaskRun, EditorialQueueItem
from app.models.content import ContentItem
from app.models.marketplace import Category, Marketplace
from app.models.product import Product

router = APIRouter(tags=["Union Autopilot & Automation"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class AutopilotRunSchema(BaseModel):
    idempotency_key: Optional[str] = None
    auto_publish_site: bool = True


class AutopilotFrequenciesSchema(BaseModel):
    discovery_minutes: int = 60
    product_update_minutes: int = 45
    content_production_minutes: int = 30
    link_review_minutes: int = 90
    campaign_monitoring_minutes: int = 40
    financial_consolidation_minutes: int = 30
    reporting_minutes: int = 120


class QueueEnqueueSchema(BaseModel):
    product_id: int
    content_id: int
    target_channel: str = "SITE"
    require_human_approval: bool = False
    campaign_id: Optional[int] = None


class QueueTransitionSchema(BaseModel):
    new_state: str


class VideoGenerateSchema(BaseModel):
    product_id: int
    aspect_ratio: str = "9:16"  # 9:16 | 16:9 | 1:1


@router.get("/autopilot", response_class=HTMLResponse)
def autopilot_page(request: Request, db: Session = Depends(get_db_session)):
    frequencies = UnionAutopilot.get_frequencies(db)
    recent_runs = db.query(AutopilotTaskRun).order_by(AutopilotTaskRun.started_at.desc()).limit(20).all()
    queue_items = db.query(EditorialQueueItem).order_by(EditorialQueueItem.created_at.desc()).limit(30).all()
    diagnostics = SystemMonitor.run_full_diagnostics(db)
    ai_status = ai_provider_router.status_report()
    link_reports = UnionLinkManager.get_link_reports(db)
    return templates.TemplateResponse(
        request,
        "autopilot.html",
        {
            "page_title": "UNION AUTOPILOT & Fila Editorial",
            "frequencies": frequencies,
            "recent_runs": recent_runs,
            "queue_items": queue_items,
            "diagnostics": diagnostics,
            "ai_status": ai_status,
            "link_reports": link_reports,
        },
    )


@router.post("/api/autopilot/run")
def api_run_autopilot_cycle(payload: AutopilotRunSchema, db: Session = Depends(get_db_session)):
    return UnionAutopilot.run_full_cycle(
        db=db,
        idempotency_key=payload.idempotency_key,
        auto_publish_site=payload.auto_publish_site,
    )


@router.post("/api/autopilot/recover")
def api_recover_interrupted_tasks(db: Session = Depends(get_db_session)):
    recovered = UnionAutopilot.recover_interrupted_tasks(db)
    return {"status": "RECOVERED", "recovered_tasks_count": recovered}


@router.get("/api/autopilot/frequencies")
def api_get_frequencies(db: Session = Depends(get_db_session)):
    return UnionAutopilot.get_frequencies(db)


@router.put("/api/autopilot/frequencies")
def api_update_frequencies(payload: AutopilotFrequenciesSchema, db: Session = Depends(get_db_session)):
    updated = UnionAutopilot.update_frequencies(db, payload.model_dump())
    return {"status": "UPDATED", "frequencies": updated}


@router.get("/api/autopilot/runs")
def api_list_autopilot_runs(limit: int = 30, db: Session = Depends(get_db_session)):
    runs = db.query(AutopilotTaskRun).order_by(AutopilotTaskRun.started_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "task_name": r.task_name,
            "idempotency_key": r.idempotency_key,
            "status": r.status,
            "attempt_count": r.attempt_count,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "result_summary": r.result_summary,
        }
        for r in runs
    ]


@router.get("/api/editorial-queue")
def api_list_editorial_queue(db: Session = Depends(get_db_session)):
    items = db.query(EditorialQueueItem).order_by(EditorialQueueItem.created_at.desc()).all()
    return [
        {
            "id": i.id,
            "product_id": i.product_id,
            "content_id": i.content_id,
            "title": i.title,
            "content_format": i.content_format,
            "target_channel": i.target_channel,
            "quality_score": i.quality_score,
            "require_human_approval": i.require_human_approval,
            "state": i.state,
            "published_url": i.published_url,
            "package_path": i.package_path,
            "error_details": i.error_details,
        }
        for i in items
    ]


@router.post("/api/editorial-queue", status_code=status.HTTP_201_CREATED)
def api_enqueue_editorial_item(payload: QueueEnqueueSchema, db: Session = Depends(get_db_session)):
    product = db.query(Product).filter(Product.id == payload.product_id).first()
    content = db.query(ContentItem).filter(ContentItem.id == payload.content_id).first()
    if not product or not content:
        raise HTTPException(status_code=404, detail="Produto ou conteúdo não encontrado.")
    engine = UnionDistributionEngine(db)
    item = engine.enqueue_editorial_item(
        product=product,
        content=content,
        target_channel=payload.target_channel,
        require_human_approval=payload.require_human_approval,
        campaign_id=payload.campaign_id,
    )
    return {
        "id": item.id,
        "state": item.state,
        "quality_score": item.quality_score,
        "dedup_hash": item.dedup_hash,
    }


@router.patch("/api/editorial-queue/{queue_id}/state")
def api_transition_queue_state(
    queue_id: int,
    payload: QueueTransitionSchema,
    db: Session = Depends(get_db_session),
):
    engine = UnionDistributionEngine(db)
    try:
        item = engine.transition_state(queue_id, payload.new_state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": item.id, "state": item.state}


@router.post("/api/editorial-queue/{queue_id}/publish")
def api_publish_queue_item(queue_id: int, db: Session = Depends(get_db_session)):
    engine = UnionDistributionEngine(db)
    try:
        return engine.publish_queue_item(queue_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/video/generate", status_code=status.HTTP_201_CREATED)
def api_generate_video(payload: VideoGenerateSchema, db: Session = Depends(get_db_session)):
    prod = db.query(Product).filter(Product.id == payload.product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    mp = db.query(Marketplace).filter(Marketplace.id == prod.marketplace_id).first()
    cat = db.query(Category).filter(Category.id == prod.category_id).first()
    return UnionVideoEngine.generate_video(
        product_title=prod.title,
        price=prod.price,
        marketplace_name=mp.name if mp else "Marketplace",
        aspect_ratio=payload.aspect_ratio,
        category_name=cat.name if cat else "Geral",
        verified_features=prod.description,
    )


@router.get("/api/links/reports")
def api_links_reports(db: Session = Depends(get_db_session)):
    return UnionLinkManager.get_link_reports(db)


@router.post("/api/links/review")
def api_review_all_links(db: Session = Depends(get_db_session)):
    return UnionLinkManager.review_all_links(db)


@router.get("/api/seo/calendar")
def api_seo_editorial_calendar(days: int = 7, db: Session = Depends(get_db_session)):
    ranked = list_ranked_opportunities(db, limit=days)
    return UnionSEOEngine.generate_editorial_calendar(ranked, days=days)


@router.post("/api/campaigns/optimize")
def api_optimize_campaigns(db: Session = Depends(get_db_session)):
    return apply_campaign_optimization_rules(db)


@router.get("/api/monitoring/diagnostics")
def api_monitoring_diagnostics(db: Session = Depends(get_db_session)):
    return SystemMonitor.run_full_diagnostics(db)


@router.get("/api/ai/status")
def api_ai_provider_status():
    return ai_provider_router.status_report()

