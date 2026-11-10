"""Ponto de entrada principal da aplicação UNION MONEY AI (FastAPI + UNION AUTOPILOT + UNION OFERTAS + UNION FINANCE AI)."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes import (
    autonomous_phase4,
    autopilot,
    campaigns,
    content,
    dashboard,
    finance,
    integrations,
    opportunities,
    products,
    publications,
    security_compliance,
    settings as settings_route,
    site,
)
from app.automation.autonomous_orchestrator import UnionAutonomousOrchestrator
from app.automation.autopilot import UnionAutopilot
from app.automation.content_jobs import run_priority_content_generation_job
from app.automation.discovery_jobs import run_rescore_all_products_job
from app.automation.financial_jobs import run_financial_reconciliation_job
from app.automation.monitoring_jobs import run_system_health_check_job
from app.automation.publication_jobs import run_landing_page_sync_job
from app.config import settings
from app.core.logging import logger
from app.core.scheduler import union_scheduler
from app.database import SessionLocal
from migrations.migration_runner import run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa migrações, recuperação de tarefas do Autopilot e agendador nativo APScheduler."""
    logger.info("Inicializando %s v%s...", settings.APP_NAME, settings.APP_VERSION)
    _ = settings.data_dir
    _ = settings.logs_dir
    _ = settings.storage_dir
    run_migrations()

    # Recupera com segurança eventuais tarefas que estavam RUNNING antes de reinicialização
    db = SessionLocal()
    try:
        UnionAutopilot.recover_interrupted_tasks(db)
        UnionAutonomousOrchestrator(db).recover_persistent_queue()
        freqs = UnionAutopilot.get_frequencies(db)
    finally:
        db.close()

    if settings.ENABLE_SCHEDULER:
        union_scheduler.register_interval_job(
            "rescore_products", run_rescore_all_products_job, minutes=freqs["product_update_minutes"]
        )
        union_scheduler.register_interval_job(
            "priority_content", run_priority_content_generation_job, minutes=freqs["content_production_minutes"]
        )
        union_scheduler.register_interval_job(
            "landing_pages_sync", run_landing_page_sync_job, minutes=freqs["campaign_monitoring_minutes"]
        )
        union_scheduler.register_interval_job(
            "financial_reconciliation", run_financial_reconciliation_job, minutes=freqs["financial_consolidation_minutes"]
        )
        union_scheduler.register_interval_job(
            "system_health_check", run_system_health_check_job, minutes=15
        )
        union_scheduler.start()

    yield

    if settings.ENABLE_SCHEDULER:
        union_scheduler.shutdown()
    logger.info("%s encerrado com segurança.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Sistema comercial autônomo de marketing de afiliados, UNION AUTOPILOT, "
        "UNION CONTENT ENGINE, UNION VIDEO ENGINE, UNION FINANCE AI e portal público UNION OFERTAS."
    ),
    lifespan=lifespan,
)

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(opportunities.router)
app.include_router(campaigns.router)
app.include_router(content.router)
app.include_router(publications.router)
app.include_router(finance.router)
app.include_router(integrations.router)
app.include_router(settings_route.router)
app.include_router(autopilot.router)
app.include_router(security_compliance.router)
app.include_router(autonomous_phase4.router)
app.include_router(site.router)


@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint de verificação de saúde da aplicação."""
    return {
        "status": "OK",
        "system": settings.APP_NAME,
        "site": settings.SITE_NAME,
        "version": settings.APP_VERSION,
        "scheduler_running": union_scheduler.scheduler.running if settings.ENABLE_SCHEDULER else False,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
