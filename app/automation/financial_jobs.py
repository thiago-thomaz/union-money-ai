"""Jobs de Reconciliação Financeira."""

from app.core.logging import logger
from app.database import SessionLocal
from app.finance.commissions import _sync_approved_commission_to_revenue_and_product
from app.models.commission import Commission


def run_financial_reconciliation_job() -> int:
    """Garante que todas as comissões APPROVED ou PAID possuam RevenueRecord vinculado."""
    db = SessionLocal()
    reconciled = 0
    try:
        approved = (
            db.query(Commission)
            .filter(Commission.status.in_(["APPROVED", "PAID"]))
            .all()
        )
        for comm in approved:
            _sync_approved_commission_to_revenue_and_product(db, comm)
            reconciled += 1
        db.commit()
        return reconciled
    except Exception as exc:
        db.rollback()
        logger.error("Erro na reconciliação financeira: %s", exc)
        return 0
    finally:
        db.close()

