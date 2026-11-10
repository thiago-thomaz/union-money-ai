"""Consolidação de Fluxo de Caixa e Patrimônio Acumulado Real."""

from typing import Any, Dict
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.config import settings
from app.models.commission import Commission
from app.models.conversion import Conversion
from app.models.financial import Expense, RevenueRecord
from app.models.product import Product


def _real_commission_query(db: Session):
    """Query base que exclui estritamente produtos sintéticos e fontes de teste (ETAPA 5)."""
    return (
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .join(Product, Product.id == Commission.product_id)
        .filter(
            Product.is_synthetic_test.is_(False),
            ~Commission.source.ilike("%SYNTHETIC%"),
            ~Commission.source.ilike("%TEST%"),
            ~Commission.source.ilike("%SANDBOX%"),
            ~Commission.source.ilike("%SIMUL%"),
        )
    )


def get_cashflow_summary(db: Session) -> Dict[str, Any]:
    """Calcula fluxo de caixa realizado sem incluir projeções, cliques ou dados sintéticos de teste."""
    confirmed_revenue = float(
        db.query(func.coalesce(func.sum(RevenueRecord.amount), 0.0))
        .outerjoin(Commission, Commission.id == RevenueRecord.commission_id)
        .outerjoin(Product, Product.id == Commission.product_id)
        .filter(
            RevenueRecord.status == "CONFIRMED",
            or_(Product.id.is_(None), Product.is_synthetic_test.is_(False)),
            ~RevenueRecord.source.ilike("%SYNTHETIC%"),
            ~RevenueRecord.source.ilike("%TEST%"),
            ~RevenueRecord.source.ilike("%SANDBOX%"),
            ~RevenueRecord.source.ilike("%SIMUL%"),
        )
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
        _real_commission_query(db)
        .filter(Commission.status == "POTENTIAL")
        .scalar()
        or 0.0
    )
    pending_commissions = float(
        _real_commission_query(db)
        .filter(Commission.status.in_(["PENDING", "ATTRIBUTED"]))
        .scalar()
        or 0.0
    )
    approved_only_commissions = float(
        _real_commission_query(db)
        .filter(Commission.status == "APPROVED")
        .scalar()
        or 0.0
    )
    paid_commissions = float(
        _real_commission_query(db)
        .filter(Commission.status == "PAID")
        .scalar()
        or 0.0
    )
    approved_commissions = round(approved_only_commissions + paid_commissions, 2)
    cancelled_commissions = float(
        _real_commission_query(db)
        .filter(Commission.status == "CANCELLED")
        .scalar()
        or 0.0
    )

    # Dados sintéticos/teste isolados para auditoria (jamais entram no caixa recebido)
    synthetic_test_commissions = float(
        db.query(func.coalesce(func.sum(Commission.amount), 0.0))
        .join(Product, Product.id == Commission.product_id)
        .filter(
            or_(
                Product.is_synthetic_test.is_(True),
                Commission.source.ilike("%SYNTHETIC%"),
                Commission.source.ilike("%TEST%"),
                Commission.source.ilike("%SANDBOX%"),
                Commission.source.ilike("%SIMUL%"),
            )
        )
        .scalar()
        or 0.0
    )
    synthetic_test_conversions = int(
        db.query(func.count(Conversion.id))
        .join(Product, Product.id == Conversion.product_id)
        .filter(
            or_(
                Product.is_synthetic_test.is_(True),
                Conversion.source.ilike("%SYNTHETIC%"),
                Conversion.source.ilike("%TEST%"),
                Conversion.source.ilike("%SANDBOX%"),
                Conversion.source.ilike("%SIMUL%"),
            )
        )
        .scalar()
        or 0
    )

    # Caixa efetivamente recebido considera SOMENTE comissões reais pagas (PAID)
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
        "test_synthetic_commissions_excluded_brl": round(synthetic_test_commissions, 2),
        "test_synthetic_conversions_excluded_count": synthetic_test_conversions,
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
