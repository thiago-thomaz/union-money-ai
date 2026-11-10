"""Rotas do UNION CONTENT ENGINE (13 Formatos + Content Quality Score + Provedores de IA)."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.content_engine.union_content_engine import UnionContentEngine
from app.dependencies import get_db_session
from app.models.content import ContentItem
from app.models.product import Product

router = APIRouter(tags=["Content"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class ContentGenerateSchema(BaseModel):
    product_id: int
    content_type: str = "ARTICLE"
    campaign_id: Optional[int] = None
    comparison_product_id: Optional[int] = None
    aspect_ratio: str = "9:16"


@router.get("/content", response_class=HTMLResponse)
def content_page(request: Request, db: Session = Depends(get_db_session)):
    contents = db.query(ContentItem).order_by(ContentItem.created_at.desc()).all()
    products = db.query(Product).filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False)).all()
    return templates.TemplateResponse(
        request,
        "content.html",
        {
            "page_title": "UNION CONTENT ENGINE",
            "contents": contents,
            "products": products,
        },
    )


@router.get("/api/content")
def api_list_content(db: Session = Depends(get_db_session)):
    items = db.query(ContentItem).order_by(ContentItem.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "product_id": c.product_id,
            "content_type": c.content_type,
            "title": c.title,
            "slug": c.slug,
            "body": c.body,
            "call_to_action": c.call_to_action,
            "media_path": c.media_path,
            "subtitle_path": c.subtitle_path,
            "aspect_ratio": c.aspect_ratio,
            "ai_provider_used": c.ai_provider_used,
            "quality_score": c.quality_score,
            "quality_breakdown": c.quality_breakdown,
            "status": c.status,
        }
        for c in items
    ]


@router.post("/api/content/generate", status_code=status.HTTP_201_CREATED)
def api_generate_content(payload: ContentGenerateSchema, db: Session = Depends(get_db_session)):
    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")

    comp_prod = None
    if payload.comparison_product_id:
        comp_prod = db.query(Product).filter(Product.id == payload.comparison_product_id).first()

    engine = UnionContentEngine(db)
    item = engine.produce(
        product=product,
        content_type=payload.content_type,
        campaign_id=payload.campaign_id,
        comparison_product=comp_prod,
        aspect_ratio=payload.aspect_ratio,
    )
    return {
        "id": item.id,
        "product_id": item.product_id,
        "content_type": item.content_type,
        "title": item.title,
        "slug": item.slug,
        "body": item.body,
        "media_path": item.media_path,
        "subtitle_path": item.subtitle_path,
        "aspect_ratio": item.aspect_ratio,
        "ai_provider_used": item.ai_provider_used,
        "quality_score": item.quality_score,
        "quality_breakdown": item.quality_breakdown,
        "status": item.status,
    }
