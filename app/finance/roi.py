"""Cálculo de ROI e EPC (Earnings Per Click) baseados exclusivamente em dados reais."""

from typing import Any, Dict
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.finance.cashflow import get_cashflow_summary
from app.models.click import ClickLog


def calculate_roi_and_epc(db: Session) -> Dict[str, Any]:
    """Calcula ROI e ganho efetivo por clique humano registrado."""
    cash = get_cashflow_summary(db)
    valid_clicks = (
        db.query(func.count(ClickLog.id))
        .filter(ClickLog.is_valid_human.is_(True))
        .scalar()
        or 0
    )

    confirmed_rev = cash["confirmed_revenue_brl"]
    expenses = cash["paid_expenses_brl"]

    epc_brl = round(confirmed_rev / valid_clicks, 4) if valid_clicks > 0 else 0.0
    if expenses > 0:
        roi_pct: float | None = round(((confirmed_rev - expenses) / expenses) * 100.0, 2)
    else:
        roi_pct = None  # Operação com custo zero inicial: ROI percentual indefinido matematicamente

    return {
        "confirmed_revenue_brl": confirmed_rev,
        "paid_expenses_brl": expenses,
        "net_profit_brl": cash["net_cashflow_brl"],
        "valid_clicks": valid_clicks,
        "epc_brl": epc_brl,
        "roi_pct": roi_pct,
        "zero_cost_operation": expenses == 0.0,
    }

