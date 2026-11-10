"""Gestão de Despesas Operacionais (Sem gastos automáticos)."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.financial import Expense, FinancialHistory


def record_expense(
    db: Session,
    source: str,
    amount: float,
    category: str = "OPERATION",
    status: str = "PAID",
    external_reference: Optional[str] = None,
    description: Optional[str] = None,
    currency: str = "BRL",
) -> Expense:
    """Registra uma despesa manual autorizada com trilha de auditoria financeira."""
    if amount <= 0:
        raise ValueError("O valor da despesa deve ser maior que zero.")

    st_upper = status.upper().strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    exp = Expense(
        source=source,
        category=category.upper().strip(),
        status=st_upper,
        amount=round(amount, 2),
        currency=currency,
        external_reference=external_reference,
        description=description,
        change_history=[
            {
                "timestamp": now_iso,
                "previous_status": None,
                "new_status": st_upper,
                "amount": round(amount, 2),
                "reason": "Registro manual de despesa",
            }
        ],
    )
    db.add(exp)
    db.flush()

    db.add(
        FinancialHistory(
            record_type="EXPENSE",
            record_uid=exp.uid,
            previous_status=None,
            new_status=st_upper,
            previous_amount=None,
            new_amount=exp.amount,
            reason="Registro manual de despesa",
        )
    )
    db.commit()
    db.refresh(exp)
    return exp

