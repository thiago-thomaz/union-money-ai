"""Análise de Funil de Marketing (Visualizações -> Cliques -> Conversões Confirmadas)."""

from typing import Any, Dict
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.click import ClickLog, VisitorAggregate
from app.models.conversion import Conversion
from app.models.publication import Publication


def get_funnel_metrics(db: Session) -> Dict[str, Any]:
    """Retorna métricas reais do funil de aquisição e conversão."""
    agg_views = db.query(func.coalesce(func.sum(VisitorAggregate.page_views), 0)).scalar() or 0
    pub_views = db.query(func.coalesce(func.sum(Publication.views_count), 0)).scalar() or 0
    views = int(agg_views + pub_views)

    valid_clicks = (
        db.query(func.count(ClickLog.id))
        .filter(ClickLog.is_valid_human.is_(True))
        .scalar()
        or 0
    )
    blocked_bot_clicks = (
        db.query(func.count(ClickLog.id))
        .filter(ClickLog.is_valid_human.is_(False))
        .scalar()
        or 0
    )
    confirmed_conversions = (
        db.query(func.count(Conversion.id))
        .filter(Conversion.status == "CONFIRMED")
        .scalar()
        or 0
    )

    return {
        "views": views,
        "valid_clicks": valid_clicks,
        "blocked_bot_clicks": blocked_bot_clicks,
        "confirmed_conversions": confirmed_conversions,
        "ctr_pct": round((valid_clicks / views) * 100.0, 2) if views > 0 else 0.0,
        "conversion_rate_pct": round((confirmed_conversions / valid_clicks) * 100.0, 2) if valid_clicks > 0 else 0.0,
    }

