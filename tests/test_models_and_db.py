"""Testes de Banco de Dados, Entidades Relacionais e Auditoria Financeira."""

from sqlalchemy.orm import Session
from app.finance.commissions import record_commission, update_commission_status
from app.finance.expenses import record_expense
from app.models.commission import Commission
from app.models.financial import FinancialHistory, RevenueRecord
from app.models.marketplace import Category, Marketplace
from app.services.product_service import create_product


def test_structural_catalog_has_10_categories_and_3_marketplaces(db_session: Session):
    categories = db_session.query(Category).all()
    marketplaces = db_session.query(Marketplace).all()

    assert len(categories) == 10
    slugs = {m.slug for m in marketplaces}
    assert slugs == {"mercadolivre", "amazon", "shopee"}


def test_financial_records_have_uid_history_and_reconciliation(db_session: Session):
    mp = db_session.query(Marketplace).filter(Marketplace.slug == "mercadolivre").first()
    cat = db_session.query(Category).filter(Category.slug == "tecnologia").first()
    assert mp and cat

    prod = create_product(
        db_session,
        {
            "title": "SSD NVMe 1TB Teste Sintético",
            "marketplace_id": mp.id,
            "category_id": cat.id,
            "price": 380.0,
            "announced_commission_rate": 8.0,
            "in_stock": True,
            "product_url": "https://www.mercadolivre.com.br/ssd-1tb",
            "is_synthetic_test": True,
            "data_source": "SYNTHETIC_TEST",
        },
    )

    comm = record_commission(
        db=db_session,
        product_id=prod.id,
        marketplace_id=mp.id,
        source="SYNTHETIC_TEST_REPORT",
        amount=30.40,
        status="PENDING",
        announced_rate_pct=8.0,
        effective_rate_pct=8.0,
        external_reference="ORD-001",
    )
    assert comm.uid is not None
    assert comm.status == "PENDING"
    assert len(comm.change_history) == 1

    # Aprova a comissão e verifica geração automática de RevenueRecord + FinancialHistory
    updated = update_commission_status(
        db=db_session,
        commission_id=comm.id,
        new_status="APPROVED",
        reason="Pagamento confirmado pelo marketplace",
    )
    assert updated.status == "APPROVED"
    assert len(updated.change_history) == 2

    rev = db_session.query(RevenueRecord).filter(RevenueRecord.commission_id == comm.id).first()
    assert rev is not None
    assert rev.amount == 30.40
    assert rev.status == "CONFIRMED"

    exp = record_expense(
        db=db_session,
        source="Dominio Anual",
        amount=40.00,
        category="INFRASTRUCTURE",
        external_reference="REG-BR-01",
    )
    assert exp.uid is not None
    assert len(exp.change_history) == 1

    histories = db_session.query(FinancialHistory).all()
    assert len(histories) >= 4

