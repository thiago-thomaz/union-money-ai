"""Gestão de Receitas Confirmadas e Agrupamento por Período."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.models.commission import Commission
from app.models.financial import FinancialHistory, RevenueRecord
from app.models.product import Product


def record_confirmed_revenue(
    db: Session,
    source: str,
    amount: float,
    marketplace_id: Optional[int] = None,
    external_reference: Optional[str] = None,
    description: Optional[str] = None,
    currency: str = "BRL",
) -> RevenueRecord:
    """Registra uma receita diretamente confirmada com histórico auditável."""
    if amount <= 0:
        raise ValueError("O valor da receita deve ser maior que zero.")

    now_iso = datetime.now(timezone.utc).isoformat()
    rev = RevenueRecord(
        marketplace_id=marketplace_id,
        source=source,
        status="CONFIRMED",
        amount=round(amount, 2),
        currency=currency,
        external_reference=external_reference,
        description=description,
        change_history=[
            {
                "timestamp": now_iso,
                "previous_status": None,
                "new_status": "CONFIRMED",
                "amount": round(amount, 2),
                "reason": "Registro de receita confirmada",
            }
        ],
    )
    db.add(rev)
    db.flush()

    db.add(
        FinancialHistory(
            record_type="REVENUE",
            record_uid=rev.uid,
            previous_status=None,
            new_status="CONFIRMED",
            previous_amount=None,
            new_amount=rev.amount,
            reason="Registro de receita confirmada",
        )
    )
    db.commit()
    db.refresh(rev)
    return rev


def get_revenue_by_period(db: Session) -> List[Dict[str, Any]]:
    """Agrupa a receita confirmada real por data (YYYY-MM-DD), excluindo dados sintéticos/teste."""
    rows = (
        db.query(
            func.strftime("%Y-%m-%d", RevenueRecord.occurred_at).label("period"),
            func.coalesce(func.sum(RevenueRecord.amount), 0.0).label("total"),
        )
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
        .group_by("period")
        .order_by("period")
        .all()
    )
    return [
        {"period": str(r.period), "confirmed_revenue_brl": round(float(r.total), 2)}
        for r in rows
        if r.period is not None and float(r.total) > 0
    ]

