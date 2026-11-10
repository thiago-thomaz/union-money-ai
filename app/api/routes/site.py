"""Rotas Públicas do Portal de Afiliados UNION OFERTAS, Sitemap XML e Robots.txt (Seções 5 e 6)."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.config import settings
from app.content_engine.quality import (
    AMAZON_ASSOCIATE_DISCLOSURE,
    STANDARD_AFFILIATE_DISCLOSURE,
)
from app.content_engine.seo import UnionSEOEngine
from app.dependencies import get_db_session
from app.marketing.link_manager import create_tracked_link
from app.models.affiliate import AffiliateLink
from app.models.click import VisitorAggregate
from app.models.content import ContentItem
from app.models.marketplace import Category, Marketplace
from app.models.product import Product

router = APIRouter(tags=["Union Ofertas Site"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


def _record_site_pageview(db: Session, channel: str = "UNION_OFERTAS", product_id: int | None = None) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    agg = (
        db.query(VisitorAggregate)
        .filter(
            VisitorAggregate.date_bucket == today,
            VisitorAggregate.channel == channel,
            VisitorAggregate.product_id == product_id,
        )
        .first()
    )
    if not agg:
        agg = VisitorAggregate(
            date_bucket=today,
            channel=channel,
            product_id=product_id,
            unique_visitors=1,
            page_views=1,
        )
        db.add(agg)
    else:
        agg.page_views += 1
    db.commit()


def _enrich_product_for_site(db: Session, prod: Product) -> Dict[str, Any]:
    mp = db.query(Marketplace).filter(Marketplace.id == prod.marketplace_id).first()
    cat = db.query(Category).filter(Category.id == prod.category_id).first()
    link = (
        db.query(AffiliateLink)
        .filter(AffiliateLink.product_id == prod.id, AffiliateLink.is_active.is_(True))
        .first()
    )
    if not link and (prod.affiliate_url or prod.product_url):
        link = create_tracked_link(db, prod, prod.affiliate_url or prod.product_url, channel="SITE")

    tracked_href = f"/r/{link.short_code}?channel=SITE" if link else (prod.affiliate_url or prod.product_url)
    mp_slug = mp.slug if mp else "mercadolivre"
    mp_name = mp.name if mp else "Marketplace"

    has_verified_discount = bool(
        prod.original_price
        and prod.price
        and prod.original_price > prod.price
        and (prod.data_verification_map or {}).get("price") == "VERIFIED"
    )

    return {
        "id": prod.id,
        "title": prod.title,
        "description": prod.description or "Descrição factual consultada na ficha pública da plataforma.",
        "price": prod.price,
        "original_price": prod.original_price if has_verified_discount else None,
        "discount_pct": prod.discount_pct if has_verified_discount else 0.0,
        "in_stock": prod.in_stock,
        "image_url": prod.image_url,
        "marketplace_name": mp_name,
        "marketplace_slug": mp_slug,
        "category_name": cat.name if cat else "Geral",
        "category_slug": cat.slug if cat else "geral",
        "updated_at_str": (prod.updated_at or prod.created_at).strftime("%d/%m/%Y %H:%M UTC"),
        "tracked_href": tracked_href,
        "opportunity_score": prod.opportunity_score,
        "score_classification": prod.score_classification,
        "is_amazon": mp_slug.lower() == "amazon",
        "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
        "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
    }


@router.get("/ofertas", response_class=HTMLResponse)
def site_home_page(request: Request, db: Session = Depends(get_db_session)):
    _record_site_pageview(db, "UNION_OFERTAS")
    raw_products = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False), Product.in_stock.is_(True))
        .order_by(Product.opportunity_score.desc().nullslast())
        .limit(12)
        .all()
    )
    products = [_enrich_product_for_site(db, p) for p in raw_products]
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
    recent_articles = (
        db.query(ContentItem)
        .filter(ContentItem.status.in_(["READY", "PUBLISHED"]))
        .order_by(ContentItem.created_at.desc())
        .limit(6)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "site/home.html",
        {
            "page_title": "UNION OFERTAS — Guias de Compra, Comparativos e Ofertas Verificadas",
            "products": products,
            "categories": categories,
            "recent_articles": recent_articles,
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/categorias", response_class=HTMLResponse)
def site_categories_page(request: Request, db: Session = Depends(get_db_session)):
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
    return templates.TemplateResponse(
        request,
        "site/categories.html",
        {
            "page_title": "Categorias Comerciais | UNION OFERTAS",
            "categories": categories,
            "selected_category": None,
            "products": [],
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/categorias/{slug}", response_class=HTMLResponse)
def site_category_detail_page(slug: str, request: Request, db: Session = Depends(get_db_session)):
    cat = db.query(Category).filter(Category.slug == slug).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    raw_products = (
        db.query(Product)
        .filter(Product.category_id == cat.id, Product.is_active.is_(True), Product.is_synthetic_test.is_(False))
        .order_by(Product.opportunity_score.desc().nullslast())
        .all()
    )
    products = [_enrich_product_for_site(db, p) for p in raw_products]
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name).all()
    return templates.TemplateResponse(
        request,
        "site/categories.html",
        {
            "page_title": f"{cat.name} | UNION OFERTAS",
            "categories": categories,
            "selected_category": cat,
            "products": products,
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/recomendados", response_class=HTMLResponse)
def site_recommended_page(request: Request, db: Session = Depends(get_db_session)):
    raw_products = (
        db.query(Product)
        .filter(
            Product.is_active.is_(True),
            Product.is_synthetic_test.is_(False),
            Product.in_stock.is_(True),
        )
        .order_by(Product.opportunity_score.desc().nullslast())
        .all()
    )
    products = [_enrich_product_for_site(db, p) for p in raw_products]
    return templates.TemplateResponse(
        request,
        "site/recommended.html",
        {
            "page_title": "Produtos Recomendados | UNION OFERTAS",
            "products": products,
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/produto/{product_id}", response_class=HTMLResponse)
def site_product_detail_page(product_id: int, request: Request, db: Session = Depends(get_db_session)):
    prod = db.query(Product).filter(Product.id == product_id, Product.is_active.is_(True)).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    _record_site_pageview(db, "UNION_OFERTAS", product_id=prod.id)
    enriched = _enrich_product_for_site(db, prod)
    related_raw = (
        db.query(Product)
        .filter(
            Product.category_id == prod.category_id,
            Product.id != prod.id,
            Product.is_active.is_(True),
            Product.is_synthetic_test.is_(False),
        )
        .limit(4)
        .all()
    )
    internal_links = UnionSEOEngine.generate_internal_links(
        current_product_id=prod.id,
        related_products=[{"id": r.id, "title": r.title} for r in related_raw],
        category_slug=enriched["category_slug"],
    )
    json_ld = UnionSEOEngine.build_structured_data_jsonld(
        product_title=prod.title,
        description=enriched["description"],
        price=prod.price,
        currency=prod.currency,
        in_stock=bool(prod.in_stock),
        product_url=f"{settings.PUBLIC_BASE_URL}/ofertas/produto/{prod.id}",
        marketplace_name=enriched["marketplace_name"],
        category_name=enriched["category_name"],
        rating=prod.rating,
        review_count=prod.review_count,
    )
    return templates.TemplateResponse(
        request,
        "site/product_detail.html",
        {
            "page_title": f"{prod.title} | UNION OFERTAS",
            "product": enriched,
            "internal_links": internal_links,
            "json_ld_str": json.dumps(json_ld, ensure_ascii=False),
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/comparativos", response_class=HTMLResponse)
def site_comparisons_page(request: Request, db: Session = Depends(get_db_session)):
    items = (
        db.query(ContentItem)
        .filter(ContentItem.content_type == "COMPARISON", ContentItem.status.in_(["READY", "PUBLISHED"]))
        .order_by(ContentItem.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "site/articles.html",
        {
            "page_title": "Comparativos de Produtos | UNION OFERTAS",
            "section_heading": "Comparativos Objetivos de Produtos",
            "articles": items,
            "selected_article": None,
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/guias", response_class=HTMLResponse)
def site_guides_page(request: Request, db: Session = Depends(get_db_session)):
    items = (
        db.query(ContentItem)
        .filter(
            ContentItem.content_type.in_(["BUYING_GUIDE", "PRODUCT_LIST"]),
            ContentItem.status.in_(["READY", "PUBLISHED"]),
        )
        .order_by(ContentItem.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "site/articles.html",
        {
            "page_title": "Guias de Compra | UNION OFERTAS",
            "section_heading": "Guias de Compra e Listas Selecionadas",
            "articles": items,
            "selected_article": None,
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/artigos", response_class=HTMLResponse)
def site_articles_list_page(request: Request, db: Session = Depends(get_db_session)):
    items = (
        db.query(ContentItem)
        .filter(ContentItem.status.in_(["READY", "PUBLISHED"]))
        .order_by(ContentItem.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "site/articles.html",
        {
            "page_title": "Artigos e Avaliações Editoriais | UNION OFERTAS",
            "section_heading": "Artigos, Análises e Guias Editoriais",
            "articles": items,
            "selected_article": None,
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/artigos/{slug}", response_class=HTMLResponse)
def site_article_detail_page(slug: str, request: Request, db: Session = Depends(get_db_session)):
    item = db.query(ContentItem).filter(ContentItem.slug == slug).first()
    if not item:
        raise HTTPException(status_code=404, detail="Artigo não encontrado.")
    _record_site_pageview(db, "UNION_OFERTAS", product_id=item.product_id)
    product = db.query(Product).filter(Product.id == item.product_id).first()
    enriched_prod = _enrich_product_for_site(db, product) if product else None
    return templates.TemplateResponse(
        request,
        "site/articles.html",
        {
            "page_title": f"{item.title} | UNION OFERTAS",
            "section_heading": item.title,
            "articles": [],
            "selected_article": item,
            "article_product": enriched_prod,
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/ofertas/{legal_page}", response_class=HTMLResponse)
def site_legal_and_institutional_pages(legal_page: str, request: Request):
    valid_pages = {
        "sobre": "Sobre o UNION OFERTAS",
        "privacidade": "Política de Privacidade (LGPD)",
        "termos": "Termos de Uso",
        "transparencia": "Transparência de Afiliados",
        "cookies": "Política de Cookies",
        "contato": "Contato e Atendimento Editorial",
        "aviso-afiliados": "Aviso de Afiliados e Transparência Comercial",
    }
    if legal_page not in valid_pages:
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    return templates.TemplateResponse(
        request,
        "site/legal.html",
        {
            "page_title": f"{valid_pages[legal_page]} | UNION OFERTAS",
            "legal_slug": legal_page,
            "heading": valid_pages[legal_page],
            "standard_disclosure": STANDARD_AFFILIATE_DISCLOSURE,
            "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        },
    )


@router.get("/sitemap.xml")
def sitemap_xml(db: Session = Depends(get_db_session)):
    urls: List[str] = [
        "/ofertas",
        "/ofertas/categorias",
        "/ofertas/recomendados",
        "/ofertas/comparativos",
        "/ofertas/guias",
        "/ofertas/artigos",
        "/ofertas/sobre",
        "/ofertas/privacidade",
        "/ofertas/cookies",
        "/ofertas/contato",
        "/ofertas/aviso-afiliados",
    ]
    cats = db.query(Category).filter(Category.is_active.is_(True)).all()
    for c in cats:
        urls.append(f"/ofertas/categorias/{c.slug}")

    prods = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.is_synthetic_test.is_(False))
        .all()
    )
    for p in prods:
        urls.append(f"/ofertas/produto/{p.id}")

    arts = db.query(ContentItem).filter(ContentItem.status.in_(["READY", "PUBLISHED"])).all()
    for a in arts:
        urls.append(f"/ofertas/artigos/{a.slug}")

    xml_str = UnionSEOEngine.build_sitemap_xml(settings.PUBLIC_BASE_URL, urls)
    return Response(content=xml_str, media_type="application/xml")


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return UnionSEOEngine.build_robots_txt(settings.PUBLIC_BASE_URL)

