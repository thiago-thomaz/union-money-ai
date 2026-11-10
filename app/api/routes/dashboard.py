"""Rotas do Painel Principal (Dashboard UNION MONEY AI) e Redirecionador de Links."""

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.intelligence.opportunity import list_ranked_opportunities
from app.intelligence.recommendation import CommercialLearningEngine
from app.marketing.link_manager import register_link_click
from app.services.reporting_service import (
    generate_pdf_executive_report,
    get_dashboard_indicators,
)

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db_session)):
    """Renderiza o Painel Principal UNION MONEY AI com dados 100% reais do banco."""
    indicators = get_dashboard_indicators(db)
    learning = CommercialLearningEngine(db).generate_learning_report()
    top_opportunities = list_ranked_opportunities(db, limit=8)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "page_title": "Painel Principal",
            "indicators": indicators,
            "learning": learning,
            "top_opportunities": top_opportunities,
        },
    )


@router.get("/api/dashboard/indicators")
def api_dashboard_indicators(include_synthetic: bool = False, db: Session = Depends(get_db_session)):
    """Retorna todos os 15 indicadores oficiais do painel em formato JSON."""
    return get_dashboard_indicators(db, include_synthetic=include_synthetic)


@router.get("/api/dashboard/learning")
def api_dashboard_learning(include_synthetic: bool = False, db: Session = Depends(get_db_session)):
    """Retorna diagnóstico do Motor de Aprendizado Comercial."""
    return CommercialLearningEngine(db).generate_learning_report(include_synthetic=include_synthetic)


@router.post("/api/dashboard/report-pdf")
def api_generate_pdf_report(db: Session = Depends(get_db_session)):
    """Gera relatório executivo em PDF usando ReportLab."""
    pdf_path = generate_pdf_executive_report(db)
    return {
        "status": "GENERATED",
        "file_name": pdf_path.name,
        "file_path": str(pdf_path),
    }


@router.get("/r/{short_code}")
def redirect_tracked_affiliate_link(
    short_code: str,
    request: Request,
    channel: str = "DIRECT",
    db: Session = Depends(get_db_session),
):
    """Registra clique real (filtrando bots) e redireciona para a URL de afiliado oficial."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    referrer = request.headers.get("referer")

    link, click = register_link_click(
        db=db,
        short_code=short_code,
        ip_address=client_ip,
        user_agent=user_agent,
        channel=channel,
        referrer=referrer,
    )
    if not link:
        raise HTTPException(status_code=404, detail="Link de afiliado não encontrado ou inativo.")

    return RedirectResponse(url=link.affiliate_url, status_code=302)

