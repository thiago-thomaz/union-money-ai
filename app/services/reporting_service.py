"""Serviço de Consolidação do Painel Principal (UNION MONEY AI) e Relatórios PDF ReportLab."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.config import settings
from app.finance.cashflow import get_cashflow_summary
from app.finance.revenue import get_revenue_by_period
from app.models.campaign import Campaign
from app.models.click import ClickLog
from app.models.commission import Commission
from app.models.content import ContentItem
from app.models.conversion import Conversion
from app.models.marketplace import Category, Marketplace
from app.models.product import Product
from app.models.publication import Publication

WAITING_REAL_DATA = "AGUARDANDO DADOS REAIS"


def get_dashboard_indicators(db: Session, include_synthetic: bool = False) -> Dict[str, Any]:
    """Consolida todos os 15 indicadores exigidos na Seção 8 sem jamais inventar números ou misturar dados de teste."""
    cash = get_cashflow_summary(db)

    click_q = db.query(func.count(ClickLog.id)).join(Product, Product.id == ClickLog.product_id).filter(
        ClickLog.is_valid_human.is_(True)
    )
    conv_q = db.query(func.count(Conversion.id)).join(Product, Product.id == Conversion.product_id).filter(
        Conversion.status == "CONFIRMED",
        ~Conversion.source.ilike("%SYNTHETIC%"),
        ~Conversion.source.ilike("%TEST%"),
        ~Conversion.source.ilike("%SANDBOX%"),
        ~Conversion.source.ilike("%SIMUL%"),
    )
    if not include_synthetic:
        click_q = click_q.filter(Product.is_synthetic_test.is_(False))
        conv_q = conv_q.filter(Product.is_synthetic_test.is_(False))

    registered_clicks = click_q.scalar() or 0
    confirmed_conversions = conv_q.scalar() or 0
    conversion_rate_pct = (
        round((confirmed_conversions / registered_clicks) * 100.0, 2)
        if registered_clicks > 0
        else 0.0
    )

    prod_q = db.query(func.count(Product.id)).filter(Product.is_active.is_(True))
    content_q = db.query(func.count(ContentItem.id)).join(Product, Product.id == ContentItem.product_id)
    pub_q = (
        db.query(func.count(Publication.id))
        .join(Product, Product.id == Publication.product_id)
        .filter(Publication.status.in_(["PUBLISHED", "EXPORTED_FOR_MANUAL"]))
    )
    if not include_synthetic:
        prod_q = prod_q.filter(Product.is_synthetic_test.is_(False))
        content_q = content_q.filter(Product.is_synthetic_test.is_(False))
        pub_q = pub_q.filter(Product.is_synthetic_test.is_(False))

    active_products = prod_q.scalar() or 0

    active_campaigns = (
        db.query(func.count(Campaign.id))
        .filter(Campaign.is_active.is_(True), Campaign.status == "ACTIVE")
        .scalar()
        or 0
    )
    produced_contents = content_q.scalar() or 0
    published_items = pub_q.scalar() or 0

    real_comm_filters = (
        Product.is_synthetic_test.is_(False),
        ~Commission.source.ilike("%SYNTHETIC%"),
        ~Commission.source.ilike("%TEST%"),
        ~Commission.source.ilike("%SANDBOX%"),
        ~Commission.source.ilike("%SIMUL%"),
    )

    # Melhor marketplace por comissões reais aprovadas ou pagas
    best_mp_row = (
        db.query(Marketplace.name, func.coalesce(func.sum(Commission.amount), 0.0).label("total"))
        .join(Commission, Commission.marketplace_id == Marketplace.id)
        .join(Product, Product.id == Commission.product_id)
        .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
        .group_by(Marketplace.id, Marketplace.name)
        .order_by(func.sum(Commission.amount).desc())
        .first()
    )
    best_marketplace = (
        f"{best_mp_row[0]} (R$ {float(best_mp_row[1]):.2f})"
        if best_mp_row and float(best_mp_row[1]) > 0
        else WAITING_REAL_DATA
    )

    # Melhor categoria por comissões reais aprovadas
    best_cat_row = (
        db.query(Category.name, func.coalesce(func.sum(Commission.amount), 0.0).label("total"))
        .join(Product, Product.category_id == Category.id)
        .join(Commission, Commission.product_id == Product.id)
        .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(Commission.amount).desc())
        .first()
    )
    best_category = (
        f"{best_cat_row[0]} (R$ {float(best_cat_row[1]):.2f})"
        if best_cat_row and float(best_cat_row[1]) > 0
        else WAITING_REAL_DATA
    )

    # Melhor produto por comissões reais aprovadas
    best_prod_row = (
        db.query(Product.title, func.coalesce(func.sum(Commission.amount), 0.0).label("total"))
        .join(Commission, Commission.product_id == Product.id)
        .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
        .group_by(Product.id, Product.title)
        .order_by(func.sum(Commission.amount).desc())
        .first()
    )
    best_product = (
        f"{best_prod_row[0]} (R$ {float(best_prod_row[1]):.2f})"
        if best_prod_row and float(best_prod_row[1]) > 0
        else WAITING_REAL_DATA
    )

    revenue_by_period = get_revenue_by_period(db)
    has_any_real_activity = (
        cash["has_real_financial_data"]
        or registered_clicks > 0
        or confirmed_conversions > 0
        or active_products > 0
        or active_campaigns > 0
        or produced_contents > 0
        or published_items > 0
    )

    return {
        "system_name": settings.APP_NAME,
        "status_banner": "OPERACIONAL COM DADOS REAIS" if has_any_real_activity else WAITING_REAL_DATA,
        "empty_data_label": WAITING_REAL_DATA,
        "confirmed_revenue_brl": cash["confirmed_revenue_brl"],
        "pending_commissions_brl": cash["pending_commissions_brl"],
        "approved_commissions_brl": cash["approved_commissions_brl"],
        "cancelled_commissions_brl": cash["cancelled_commissions_brl"],
        "paid_expenses_brl": cash["paid_expenses_brl"],
        "net_cashflow_brl": cash["net_cashflow_brl"],
        "registered_clicks": registered_clicks,
        "confirmed_conversions": confirmed_conversions,
        "conversion_rate_pct": conversion_rate_pct,
        "active_products": active_products,
        "active_campaigns": active_campaigns,
        "produced_contents": produced_contents,
        "published_items": published_items,
        "best_marketplace": best_marketplace,
        "best_category": best_category,
        "best_product": best_product,
        "revenue_by_period": revenue_by_period,
        "revenue_chart_status": "READY" if len(revenue_by_period) > 0 else WAITING_REAL_DATA,
        "long_term_goal_brl": cash["long_term_goal_brl"],
        "realized_goal_progress_pct": cash["realized_goal_progress_pct"],
    }


def generate_pdf_executive_report(db: Session, filename: str | None = None) -> Path:
    """Gera relatório executivo em PDF utilizando ReportLab com os indicadores reais do banco."""
    indicators = get_dashboard_indicators(db)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = filename or f"relatorio_union_money_ai_{ts}.pdf"
    out_path = settings.storage_dir / "reports" / fname

    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 55, "UNION MONEY AI - RELATORIO EXECUTIVO OPERACIONAL")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 73, f"Gerado em (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, height - 88, f"Status do Painel: {indicators['status_banner']}")

    y = height - 125
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "1. Indicadores Financeiros e de Conversao")
    y -= 22

    c.setFont("Helvetica", 10)
    rows = [
        f"Receita Confirmada: R$ {indicators['confirmed_revenue_brl']:.2f}",
        f"Comissoes Pendentes: R$ {indicators['pending_commissions_brl']:.2f}",
        f"Comissoes Aprovadas: R$ {indicators['approved_commissions_brl']:.2f}",
        f"Comissoes Canceladas: R$ {indicators['cancelled_commissions_brl']:.2f}",
        f"Despesas Pagas: R$ {indicators['paid_expenses_brl']:.2f}",
        f"Saldo Liquido Realizado: R$ {indicators['net_cashflow_brl']:.2f}",
        f"Cliques Registrados (Humanos): {indicators['registered_clicks']}",
        f"Conversoes Confirmadas: {indicators['confirmed_conversions']}",
        f"Taxa de Conversao: {indicators['conversion_rate_pct']:.2f}%",
        f"Produtos Ativos: {indicators['active_products']}",
        f"Campanhas Ativas: {indicators['active_campaigns']}",
        f"Conteudos Produzidos: {indicators['produced_contents']}",
        f"Publicacoes Realizadas: {indicators['published_items']}",
        f"Melhor Marketplace: {indicators['best_marketplace']}",
        f"Melhor Categoria: {indicators['best_category']}",
        f"Melhor Produto: {indicators['best_product']}",
    ]

    for line in rows:
        c.drawString(60, y, line)
        y -= 18

    y -= 15
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        50,
        y,
        "Nota de Integridade: Nenhuma venda simulada ou comissao ficticia e contabilizada neste relatorio.",
    )
    c.showPage()
    c.save()
    return out_path

