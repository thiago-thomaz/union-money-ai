"""Rotas Web e API REST para CRUD Completo de Produtos."""

from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.models.marketplace import Category, Marketplace
from app.services.product_service import (
    create_product,
    delete_product,
    get_product_by_id,
    list_products,
    update_product,
)

router = APIRouter(tags=["Products"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class ProductCreateSchema(BaseModel):
    external_id: Optional[str] = None
    title: str = Field(..., min_length=3, max_length=280)
    description: Optional[str] = None
    marketplace_id: int
    category_id: int
    price: float = Field(..., gt=0)
    original_price: Optional[float] = None
    announced_commission_rate: Optional[float] = Field(default=None, ge=0, le=100)
    effective_commission_rate: Optional[float] = Field(default=None, ge=0, le=100)
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    review_count: Optional[int] = Field(default=None, ge=0)
    seller_reputation: Optional[str] = None
    demand_index: Optional[float] = Field(default=None, ge=0, le=100)
    competition_index: Optional[float] = Field(default=None, ge=0, le=100)
    content_potential_index: Optional[float] = Field(default=None, ge=0, le=100)
    utility_score: Optional[float] = Field(default=None, ge=0, le=100)
    in_stock: Optional[bool] = True
    product_url: str = Field(..., min_length=8)
    affiliate_url: Optional[str] = None
    image_url: Optional[str] = None
    data_verification_map: Optional[Dict[str, str]] = None
    data_source: str = "MANUAL_VERIFIED"
    is_synthetic_test: bool = False


class ProductUpdateSchema(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    marketplace_id: Optional[int] = None
    category_id: Optional[int] = None
    price: Optional[float] = Field(default=None, gt=0)
    original_price: Optional[float] = None
    announced_commission_rate: Optional[float] = Field(default=None, ge=0, le=100)
    effective_commission_rate: Optional[float] = Field(default=None, ge=0, le=100)
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    review_count: Optional[int] = Field(default=None, ge=0)
    demand_index: Optional[float] = Field(default=None, ge=0, le=100)
    competition_index: Optional[float] = Field(default=None, ge=0, le=100)
    content_potential_index: Optional[float] = Field(default=None, ge=0, le=100)
    utility_score: Optional[float] = Field(default=None, ge=0, le=100)
    in_stock: Optional[bool] = None
    product_url: Optional[str] = None
    affiliate_url: Optional[str] = None
    data_verification_map: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None


def _serialize_product(prod) -> Dict[str, Any]:
    return {
        "id": prod.id,
        "external_id": prod.external_id,
        "title": prod.title,
        "description": prod.description,
        "marketplace_id": prod.marketplace_id,
        "category_id": prod.category_id,
        "price": prod.price,
        "original_price": prod.original_price,
        "discount_pct": prod.discount_pct,
        "announced_commission_rate": prod.announced_commission_rate,
        "effective_commission_rate": prod.effective_commission_rate,
        "estimated_commission_value": prod.estimated_commission_value,
        "rating": prod.rating,
        "review_count": prod.review_count,
        "demand_index": prod.demand_index,
        "competition_index": prod.competition_index,
        "content_potential_index": prod.content_potential_index,
        "utility_score": prod.utility_score,
        "in_stock": prod.in_stock,
        "product_url": prod.product_url,
        "affiliate_url": prod.affiliate_url,
        "data_source": prod.data_source,
        "is_synthetic_test": prod.is_synthetic_test,
        "opportunity_score": prod.opportunity_score,
        "score_classification": prod.score_classification,
        "confidence_score": prod.confidence_score,
        "score_breakdown": prod.score_breakdown,
        "is_active": prod.is_active,
        "created_at": prod.created_at.isoformat() if prod.created_at else None,
    }


@router.get("/products", response_class=HTMLResponse)
def products_page(request: Request, db: Session = Depends(get_db_session)):
    products = list_products(db, include_synthetic=False, only_active=True)
    marketplaces = db.query(Marketplace).filter(Marketplace.is_active.is_(True)).all()
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
    return templates.TemplateResponse(
        request,
        "products.html",
        {
            "page_title": "Catálogo de Produtos",
            "products": products,
            "marketplaces": marketplaces,
            "categories": categories,
        },
    )


@router.get("/api/products")
def api_list_products(
    include_synthetic: bool = False,
    only_active: bool = True,
    marketplace_id: Optional[int] = None,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db_session),
):
    items = list_products(
        db,
        include_synthetic=include_synthetic,
        only_active=only_active,
        marketplace_id=marketplace_id,
        category_id=category_id,
    )
    return [_serialize_product(p) for p in items]


@router.post("/api/products", status_code=status.HTTP_201_CREATED)
def api_create_product(payload: ProductCreateSchema, db: Session = Depends(get_db_session)):
    try:
        product = create_product(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_product(product)


@router.get("/api/products/{product_id}")
def api_get_product(product_id: int, db: Session = Depends(get_db_session)):
    product = get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return _serialize_product(product)


@router.put("/api/products/{product_id}")
def api_update_product(product_id: int, payload: ProductUpdateSchema, db: Session = Depends(get_db_session)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        product = update_product(db, product_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_product(product)


@router.delete("/api/products/{product_id}")
def api_delete_product(product_id: int, hard_delete: bool = False, db: Session = Depends(get_db_session)):
    deleted = delete_product(db, product_id, hard_delete=hard_delete)
    if not deleted:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return {"status": "DELETED", "product_id": product_id, "hard_delete": hard_delete}

