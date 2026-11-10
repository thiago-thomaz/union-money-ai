"""Gestão de Comissões (Pendentes, Aprovadas, Canceladas) com Histórico Imutável."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.commission import Commission
from app.models.financial import FinancialHistory, RevenueRecord
from app.models.product import Product


def record_commission(
    db: Session,
    product_id: int,
    marketplace_id: int,
    source: str,
    amount: float,
    status: str = "PENDING",
    currency: str = "BRL",
    conversion_id: Optional[int] = None,
    announced_rate_pct: Optional[float] = None,
    effective_rate_pct: Optional[float] = None,
    external_reference: Optional[str] = None,
) -> Commission:
    """Registra uma comissão com trilha de auditoria financeira obrigatória."""
    if amount < 0:
        raise ValueError("O valor da comissão não pode ser negativo.")

    now_iso = datetime.now(timezone.utc).isoformat()
    st_upper = status.upper().strip()
    initial_entry = {
        "timestamp": now_iso,
        "previous_status": None,
        "new_status": st_upper,
        "amount": round(amount, 2),
        "reason": "Criação inicial do registro de comissão",
    }

    commission = Commission(
        conversion_id=conversion_id,
        product_id=product_id,
        marketplace_id=marketplace_id,
        source=source,
        status=st_upper,
        amount=round(amount, 2),
        currency=currency,
        announced_rate_pct=announced_rate_pct,
        effective_rate_pct=effective_rate_pct,
        external_reference=external_reference,
        change_history=[initial_entry],
    )
    db.add(commission)
    db.flush()

    hist = FinancialHistory(
        record_type="COMMISSION",
        record_uid=commission.uid,
        previous_status=None,
        new_status=st_upper,
        previous_amount=None,
        new_amount=round(amount, 2),
        reason="Criação inicial do registro de comissão",
    )
    db.add(hist)

    # Se já nascer APPROVED ou PAID, atualiza taxa efetiva do produto e gera receita confirmada
    if st_upper in ("APPROVED", "PAID"):
        _sync_approved_commission_to_revenue_and_product(db, commission)

    db.commit()
    db.refresh(commission)
    return commission


def update_commission_status(
    db: Session,
    commission_id: int,
    new_status: str,
    reason: str = "Atualização de status de comissão",
    new_amount: Optional[float] = None,
) -> Commission:
    """Atualiza o status/valor de uma comissão preservando histórico completo de alterações."""
    commission = db.query(Commission).filter(Commission.id == commission_id).first()
    if not commission:
        raise ValueError(f"Comissão {commission_id} não encontrada.")

    prev_status = commission.status
    prev_amount = commission.amount
    st_upper = new_status.upper().strip()
    amt = round(new_amount if new_amount is not None else commission.amount, 2)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "previous_status": prev_status,
        "new_status": st_upper,
        "previous_amount": prev_amount,
        "amount": amt,
        "reason": reason,
    }
    history_list = list(commission.change_history or [])
    history_list.append(entry)

    commission.status = st_upper
    commission.amount = amt
    commission.change_history = history_list

    hist = FinancialHistory(
        record_type="COMMISSION",
        record_uid=commission.uid,
        previous_status=prev_status,
        new_status=st_upper,
        previous_amount=prev_amount,
        new_amount=amt,
        reason=reason,
    )
    db.add(hist)

    if st_upper in ("APPROVED", "PAID") and prev_status not in ("APPROVED", "PAID"):
        _sync_approved_commission_to_revenue_and_product(db, commission)

    db.commit()
    db.refresh(commission)
    return commission


def _sync_approved_commission_to_revenue_and_product(db: Session, commission: Commission) -> None:
    """Cria registro de Receita Confirmada correspondente e atualiza taxa efetiva do produto."""
    existing_rev = (
        db.query(RevenueRecord)
        .filter(RevenueRecord.commission_id == commission.id)
        .first()
    )
    if not existing_rev:
        now_iso = datetime.now(timezone.utc).isoformat()
        rev = RevenueRecord(
            commission_id=commission.id,
            marketplace_id=commission.marketplace_id,
            source=commission.source,
            status="CONFIRMED",
            amount=commission.amount,
            currency=commission.currency,
            external_reference=commission.external_reference,
            description=f"Receita confirmada oriunda da comissão UID {commission.uid}",
            change_history=[
                {
                    "timestamp": now_iso,
                    "previous_status": None,
                    "new_status": "CONFIRMED",
                    "amount": commission.amount,
                    "reason": "Aprovação de comissão vinculada",
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
                reason="Aprovação de comissão vinculada",
            )
        )

    if commission.effective_rate_pct is not None:
        product = db.query(Product).filter(Product.id == commission.product_id).first()
        if product:
            product.effective_commission_rate = commission.effective_rate_pct

