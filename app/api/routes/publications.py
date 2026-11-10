"""Rotas de Publicações e Distribuição Multicanal."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.marketing.distribution import distribute_content
from app.marketing.landing_pages import build_product_landing_page
from app.models.content import ContentItem
from app.models.marketplace import Marketplace
from app.models.product import Product
from app.models.publication import Publication

router = APIRouter(tags=["Publications"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


class PublicationCreateSchema(BaseModel):
    content_id: int
    channel: str = "LANDING_PAGE"  # LANDING_PAGE | YOUTUBE | INSTAGRAM | PINTEREST
    published_url: Optional[str] = None


@router.get("/publications", response_class=HTMLResponse)
def publications_page(request: Request, db: Session = Depends(get_db_session)):
    publications = db.query(Publication).order_by(Publication.created_at.desc()).all()
    contents = db.query(ContentItem).order_by(ContentItem.created_at.desc()).all()
    return templates.TemplateResponse(
        request,
        "publications.html",
        {
            "page_title": "Publicações e Distribuição",
            "publications": publications,
            "contents": contents,
        },
    )


@router.get("/api/publications")
def api_list_publications(db: Session = Depends(get_db_session)):
    pubs = db.query(Publication).order_by(Publication.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "content_id": p.content_id,
            "product_id": p.product_id,
            "channel": p.channel,
            "published_url": p.published_url,
            "status": p.status,
            "views_count": p.views_count,
            "published_at": p.published_at.isoformat() if p.published_at else None,
        }
        for p in pubs
    ]


@router.post("/api/publications", status_code=status.HTTP_201_CREATED)
def api_create_publication(payload: PublicationCreateSchema, db: Session = Depends(get_db_session)):
    content = db.query(ContentItem).filter(ContentItem.id == payload.content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado.")

    pub_url = payload.published_url
    if payload.channel.upper().strip() == "LANDING_PAGE" and not pub_url:
        product = db.query(Product).filter(Product.id == content.product_id).first()
        if product:
            mp = db.query(Marketplace).filter(Marketplace.id == product.marketplace_id).first()
            lp_path = build_product_landing_page(
                product,
                marketplace_name=mp.name if mp else "Marketplace",
                tracked_url=product.affiliate_url or product.product_url,
            )
            pub_url = str(lp_path)

    return distribute_content(db, content=content, channel=payload.channel, published_url=pub_url)

