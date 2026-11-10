"""Serviço de Afiliados, Conversões e Comissões."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.finance.commissions import record_commission
from app.models.affiliate import AffiliateAccount
from app.models.conversion import Conversion
from app.models.financial import FinancialHistory
from app.models.product import Product


def register_affiliate_account(
    db: Session,
    marketplace_id: int,
    account_label: str,
    affiliate_tag: str,
    has_api_credentials: bool = False,
) -> AffiliateAccount:
    account = AffiliateAccount(
        marketplace_id=marketplace_id,
        account_label=account_label.strip(),
        affiliate_tag=affiliate_tag.strip(),
        api_Status="API_ACTIVE" if has_api_credentials else "MANUAL_ONLY",
        has_api_credentials=has_api_credentials,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def record_real_conversion(
    db: Session,
    product_id: int,
    source: str,
    order_value: float,
    commission_amount: Optional[float] = None,
    commission_status: str = "PENDING",
    channel: str = "DIRECT",
    content_format: str = "ARTICLE",
    quantity: int = 1,
    status: str = "CONFIRMED",
    external_reference: Optional[str] = None,
    campaign_id: Optional[int] = None,
    click_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Registra uma conversão confirmada/reportada pelo marketplace e sua respectiva comissão."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise ValueError(f"Produto {product_id} não encontrado.")
    if order_value <= 0:
        raise ValueError("O valor do pedido deve ser maior que zero.")

    st_upper = status.upper().strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    conv = Conversion(
        product_id=product.id,
        marketplace_id=product.marketplace_id,
        campaign_id=campaign_id,
        click_id=click_id,
        source=source,
        channel=channel.upper().strip(),
        content_format=content_format.upper().strip(),
        quantity=max(1, quantity),
        order_value=round(order_value, 2),
        currency="BRL",
        status=st_upper,
        external_reference=external_reference,
        change_history=[
            {
                "timestamp": now_iso,
                "previous_status": None,
                "new_status": st_upper,
                "amount": round(order_value, 2),
                "reason": "Registro de conversão de venda",
            }
        ],
    )
    db.add(conv)
    db.flush()

    db.add(
        FinancialHistory(
            record_type="CONVERSION",
            record_uid=conv.uid,
            previous_status=None,
            new_status=st_upper,
            previous_amount=None,
            new_amount=conv.order_value,
            reason="Registro de conversão de venda",
        )
    )

    commission_obj = None
    if commission_amount is not None and commission_amount >= 0:
        effective_rate = round((commission_amount / order_value) * 100.0, 2) if order_value > 0 else None
        commission_obj = record_commission(
            db=db,
            product_id=product.id,
            marketplace_id=product.marketplace_id,
            source=source,
            amount=commission_amount,
            status=commission_status,
            conversion_id=conv.id,
            announced_rate_pct=product.announced_commission_rate,
            effective_rate_pct=effective_rate,
            external_reference=external_reference,
        )
    else:
        db.commit()
        db.refresh(conv)

    return {
        "conversion_id": conv.id,
        "conversion_uid": conv.uid,
        "commission_id": commission_obj.id if commission_obj else None,
        "commission_uid": commission_obj.uid if commission_obj else None,
    }

