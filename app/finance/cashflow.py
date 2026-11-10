"""Consolidação de Fluxo de Caixa e Patrimônio Acumulado Real."""

from typing import Any, Dict
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.config import settings
from app.models.commission import Commission
from app.models.financial import Expense, RevenueRecord


def get_cashflow_summary(db: Session) -> Dict[str, Any]:
    """Calcula fluxo de caixa realizado sem incluir projeções ou cliques."""
    confirmed_revenue = float(
        db.query(func.coalesce(func.sum(RevenueRecord.amount), 0.0))
        .filter(RevenueRecord.status == "CONFIRMED")
        .scalar()
        or 0.0
    )
    paid_expenses = float(
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.status == "PAID")
        .scalar()
        or 0.0
    )
    potential_commissions = float(
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .filter(Commission.status == "POTENTIAL")
        .scalar()
        or 0.0
    )
    pending_commissions = float(
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .filter(Commission.status.in_(["PENDING", "ATTRIBUTED"]))
        .scalar()
        or 0.0
    )
    approved_only_commissions = float(
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .filter(Commission.status == "APPROVED")
        .scalar()
        or 0.0
    )
    paid_commissions = float(
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .filter(Commission.status == "PAID")
        .scalar()
        or 0.0
    )
    approved_commissions = round(approved_only_commissions + paid_commissions, 2)
    cancelled_commissions = float(
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .filter(Commission.status == "CANCELLED")
        .scalar()
        or 0.0
    )

    # Caixa efetivamente recebido considera SOMENTE comissões pagas (PAID)
    cash_received = round(paid_commissions - paid_expenses, 2)
    net_cashflow = round(confirmed_revenue - paid_expenses, 2)
    goal = settings.LONG_TERM_PATRIMONY_GOAL_BRL
    goal_progress_pct = round((max(0.0, net_cashflow) / goal) * 100.0, 4) if goal > 0 else 0.0

    return {
        "confirmed_revenue_brl": round(confirmed_revenue, 2),
        "paid_expenses_brl": round(paid_expenses, 2),
        "net_cashflow_brl": net_cashflow,
        "cash_received_brl": round(paid_commissions, 2),
        "net_cash_received_brl": cash_received,
        "potential_commissions_brl": round(potential_commissions, 2),
        "pending_commissions_brl": round(pending_commissions, 2),
        "approved_only_commissions_brl": round(approved_only_commissions, 2),
        "approved_commissions_brl": round(approved_commissions, 2),
        "paid_commissions_brl": round(paid_commissions, 2),
        "cancelled_commissions_brl": round(cancelled_commissions, 2),
        "long_term_goal_brl": goal,
        "realized_goal_progress_pct": goal_progress_pct,
        "has_real_financial_data": (
            confirmed_revenue > 0
            or paid_expenses > 0
            or pending_commissions > 0
            or approved_commissions > 0
            or paid_commissions > 0
            or cancelled_commissions > 0
        ),
    }
