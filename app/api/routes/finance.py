"""Rotas Financeiras: UNION FINANCE AI, Comissões 5 Estágios, CSV Oficial, Conciliação, UNION WEALTH SIMULATOR e UNION GROWTH MANAGER."""

from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.finance.cashflow import get_cashflow_summary
from app.finance.commissions import record_commission, update_commission_status
from app.finance.expenses import record_expense
from app.finance.growth_manager import UnionGrowthManager
from app.finance.projections import get_transparent_projections
from app.finance.revenue import get_revenue_by_period, record_confirmed_revenue
from app.finance.roi import calculate_roi_and_epc
from app.finance.union_finance_ai import UnionFinanceAI
from app.finance.wealth_simulator import UnionWealthSimulator
from app.models.commission import Commission
from app.models.conversion import Conversion
from app.models.financial import Expense, FinancialHistory, RevenueRecord
from app.models.product import Product
from app.services.affiliate_service import record_real_conversion

router = APIRouter(tags=["Finance"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class ConversionCreateSchema(BaseModel):
    product_id: int
    source: str = Field(..., min_length=2)
    order_value: float = Field(..., gt=0)
    commission_amount: Optional[float] = Field(default=None, ge=0)
    commission_status: str = "PENDING"
    channel: str = "DIRECT"
    content_format: str = "ARTICLE"
    quantity: int = 1
    status: str = "CONFIRMED"
    external_reference: Optional[str] = None
    campaign_id: Optional[int] = None


class CommissionCreateSchema(BaseModel):
    product_id: int
    marketplace_id: int
    source: str = Field(..., min_length=2)
    amount: float = Field(..., ge=0)
    status: str = "PENDING"
    announced_rate_pct: Optional[float] = None
    effective_rate_pct: Optional[float] = None
    external_reference: Optional[str] = None


class CommissionStatusUpdateSchema(BaseModel):
    status: str
    reason: str = "Atualização de status de comissão"
    new_amount: Optional[float] = None


class RevenueCreateSchema(BaseModel):
    source: str = Field(..., min_length=2)
    amount: float = Field(..., gt=0)
    marketplace_id: Optional[int] = None
    external_reference: Optional[str] = None
    description: Optional[str] = None


class ExpenseCreateSchema(BaseModel):
    source: str = Field(..., min_length=2)
    amount: float = Field(..., gt=0)
    category: str = "OPERATION"
    status: str = "PAID"
    external_reference: Optional[str] = None
    description: Optional[str] = None


class CSVImportSchema(BaseModel):
    marketplace_slug: str = "mercadolivre"
    csv_content: str = Field(..., min_length=10)


class WealthSimulatorSchema(BaseModel):
    scenario: str = "MODERADO"
    custom_vars: Optional[Dict[str, float]] = None


class GrowthAllocationUpdateSchema(BaseModel):
    cash_reserve_pct: float = 30.0
    infrastructure_pct: float = 10.0
    content_production_pct: float = 20.0
    organic_growth_pct: float = 15.0
    optional_tools_pct: float = 5.0
    tax_reserve_pct: float = 10.0
    available_profit_pct: float = 10.0


@router.get("/finance", response_class=HTMLResponse)
def finance_page(request: Request, db: Session = Depends(get_db_session)):
    cashflow = get_cashflow_summary(db)
    roi = calculate_roi_and_epc(db)
    projections = get_transparent_projections(db)
    finance_ai = UnionFinanceAI(db).get_full_indicators()
    wealth_sim = UnionWealthSimulator(db).simulate("MODERADO")
    growth_rec = UnionGrowthManager(db).recommend_reinvestment()
    commissions = db.query(Commission).order_by(Commission.created_at.desc()).limit(50).all()
    revenues = db.query(RevenueRecord).order_by(RevenueRecord.created_at.desc()).limit(50).all()
    expenses = db.query(Expense).order_by(Expense.created_at.desc()).limit(50).all()
    conversions = db.query(Conversion).order_by(Conversion.created_at.desc()).limit(50).all()
    products = db.query(Product).filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False)).all()
    return templates.TemplateResponse(
        request,
        "finance.html",
        {
            "page_title": "UNION FINANCE AI — Gestão Financeira, Simulador e Reinvestimento",
            "cashflow": cashflow,
            "roi": roi,
            "projections": projections,
            "finance_ai": finance_ai,
            "wealth_sim": wealth_sim,
            "growth_rec": growth_rec,
            "commissions": commissions,
            "revenues": revenues,
            "expenses": expenses,
            "conversions": conversions,
            "products": products,
        },
    )


@router.get("/api/finance/summary")
def api_finance_summary(db: Session = Depends(get_db_session)):
    return {
        "cashflow": get_cashflow_summary(db),
        "roi_and_epc": calculate_roi_and_epc(db),
        "revenue_by_period": get_revenue_by_period(db),
        "projections": get_transparent_projections(db),
        "union_finance_ai": UnionFinanceAI(db).get_full_indicators(),
    }


@router.get("/api/finance/indicators")
def api_finance_indicators(db: Session = Depends(get_db_session)):
    return UnionFinanceAI(db).get_full_indicators()


@router.post("/api/finance/import-csv")
def api_import_csv_report(payload: CSVImportSchema, db: Session = Depends(get_db_session)):
    try:
        return UnionFinanceAI(db).import_official_csv_report(
            csv_content=payload.csv_content,
            marketplace_slug=payload.marketplace_slug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/finance/reconcile")
def api_reconcile_commissions(db: Session = Depends(get_db_session)):
    return UnionFinanceAI(db).reconcile_commissions()


@router.get("/api/finance/wealth-simulator")
def api_get_wealth_simulator(scenario: str = "MODERADO", db: Session = Depends(get_db_session)):
    return UnionWealthSimulator(db).simulate(scenario=scenario)


@router.post("/api/finance/wealth-simulator")
def api_post_wealth_simulator(payload: WealthSimulatorSchema, db: Session = Depends(get_db_session)):
    return UnionWealthSimulator(db).simulate(
        scenario=payload.scenario,
        custom_vars=payload.custom_vars,
    )


@router.get("/api/finance/growth-manager")
def api_get_growth_manager(db: Session = Depends(get_db_session)):
    return UnionGrowthManager(db).recommend_reinvestment()


@router.put("/api/finance/growth-manager/weights")
def api_update_growth_weights(payload: GrowthAllocationUpdateSchema, db: Session = Depends(get_db_session)):
    try:
        weights = UnionGrowthManager(db).update_allocation_weights(payload.model_dump())
        return {
            "status": "UPDATED",
            "weights": weights,
            "recommendation": UnionGrowthManager(db).recommend_reinvestment(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/finance/conversions", status_code=status.HTTP_201_CREATED)
def api_create_conversion(payload: ConversionCreateSchema, db: Session = Depends(get_db_session)):
    try:
        return record_real_conversion(
            db=db,
            product_id=payload.product_id,
            source=payload.source,
            order_value=payload.order_value,
            commission_amount=payload.commission_amount,
            commission_status=payload.commission_status,
            channel=payload.channel,
            content_format=payload.content_format,
            quantity=payload.quantity,
            status=payload.status,
            external_reference=payload.external_reference,
            campaign_id=payload.external_reference and payload.campaign_id or payload.campaign_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/finance/commissions", status_code=status.HTTP_201_CREATED)
def api_create_commission(payload: CommissionCreateSchema, db: Session = Depends(get_db_session)):
    try:
        comm = record_commission(
            db=db,
            product_id=payload.product_id,
            marketplace_id=payload.marketplace_id,
            source=payload.source,
            amount=payload.amount,
            status=payload.status,
            announced_rate_pct=payload.announced_rate_pct,
            effective_rate_pct=payload.effective_rate_pct,
            external_reference=payload.external_reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "id": comm.id,
        "uid": comm.uid,
        "status": comm.status,
        "amount": comm.amount,
        "currency": comm.currency,
        "external_reference": comm.external_reference,
        "change_history": comm.change_history,
    }


@router.patch("/api/finance/commissions/{commission_id}")
def api_update_commission(
    commission_id: int,
    payload: CommissionStatusUpdateSchema,
    db: Session = Depends(get_db_session),
):
    try:
        comm = update_commission_status(
            db=db,
            commission_id=commission_id,
            new_status=payload.status,
            reason=payload.reason,
            new_amount=payload.new_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "id": comm.id,
        "uid": comm.uid,
        "status": comm.status,
        "amount": comm.amount,
        "change_history": comm.change_history,
    }


@router.post("/api/finance/revenues", status_code=status.HTTP_201_CREATED)
def api_create_revenue(payload: RevenueCreateSchema, db: Session = Depends(get_db_session)):
    rev = record_confirmed_revenue(
        db=db,
        source=payload.source,
        amount=payload.amount,
        marketplace_id=payload.marketplace_id,
        external_reference=payload.external_reference,
        description=payload.description,
    )
    return {
        "id": rev.id,
        "uid": rev.uid,
        "status": rev.status,
        "amount": rev.amount,
        "currency": rev.currency,
        "change_history": rev.change_history,
    }


@router.post("/api/finance/expenses", status_code=status.HTTP_201_CREATED)
def api_create_expense(payload: ExpenseCreateSchema, db: Session = Depends(get_db_session)):
    exp = record_expense(
        db=db,
        source=payload.source,
        amount=payload.amount,
        category=payload.category,
        status=payload.status,
        external_reference=payload.external_reference,
        description=payload.description,
    )
    return {
        "id": exp.id,
        "uid": exp.uid,
        "status": exp.status,
        "amount": exp.amount,
        "currency": exp.currency,
        "change_history": exp.change_history,
    }


@router.get("/api/finance/history")
def api_finance_history(limit: int = 100, db: Session = Depends(get_db_session)):
    rows = db.query(FinancialHistory).order_by(FinancialHistory.changed_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "record_type": r.record_type,
            "record_uid": r.record_uid,
            "previous_status": r.previous_status,
            "new_status": r.new_status,
            "previous_amount": r.previous_amount,
            "new_amount": r.new_amount,
            "reason": r.reason,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        }
        for r in rows
    ]
