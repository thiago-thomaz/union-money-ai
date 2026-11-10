"""Serviço de Produtos (CRUD Completo + Motor de Pontuação + Auditoria)."""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.intelligence.discovery import get_connector
from app.intelligence.opportunity import score_and_update_product
from app.marketing.link_manager import create_tracked_link
from app.models.audit import AuditLog
from app.models.marketplace import Category, Marketplace
from app.models.product import Product


def create_product(db: Session, payload: Dict[str, Any]) -> Product:
    """Cria um produto, gera seu link de afiliado, calcula o Product Opportunity Score e persiste."""
    marketplace_id = int(payload["marketplace_id"])
    category_id = int(payload["category_id"])

    mp = db.query(Marketplace).filter(Marketplace.id == marketplace_id).first()
    if not mp:
        raise ValueError(f"Marketplace ID {marketplace_id} não encontrado.")
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise ValueError(f"Categoria ID {category_id} não encontrada.")

    price = float(payload["price"])
    orig_price = float(payload["original_price"]) if payload.get("original_price") is not None else None
    discount_pct = 0.0
    if orig_price and orig_price > price > 0:
        discount_pct = round(((orig_price - price) / orig_price) * 100.0, 2)

    product_url = str(payload["product_url"]).strip()
    affiliate_url = payload.get("affiliate_url")
    if not affiliate_url:
        try:
            connector = get_connector(mp.slug)
            affiliate_url = connector.build_affiliate_link(product_url)
        except Exception:
            affiliate_url = product_url

    verification_map = payload.get("data_verification_map") or {
        "price": "VERIFIED",
        "in_stock": "VERIFIED",
        "announced_commission_rate": "VERIFIED" if payload.get("announced_commission_rate") is not None else "UNAVAILABLE",
        "rating": "VERIFIED" if payload.get("rating") is not None else "UNAVAILABLE",
        "demand_index": "ESTIMATED" if payload.get("demand_index") is not None else "UNAVAILABLE",
        "competition_index": "ESTIMATED" if payload.get("competition_index") is not None else "UNAVAILABLE",
        "content_potential_index": "ESTIMATED" if payload.get("content_potential_index") is not None else "UNAVAILABLE",
    }

    product = Product(
        external_id=payload.get("external_id"),
        title=str(payload["title"]).strip(),
        description=payload.get("description"),
        marketplace_id=marketplace_id,
        category_id=category_id,
        price=price,
        original_price=orig_price,
        currency=payload.get("currency", "BRL"),
        discount_pct=discount_pct,
        announced_commission_rate=payload.get("announced_commission_rate"),
        effective_commission_rate=payload.get("effective_commission_rate"),
        rating=payload.get("rating"),
        review_count=payload.get("review_count"),
        seller_reputation=payload.get("seller_reputation"),
        demand_index=payload.get("demand_index"),
        competition_index=payload.get("competition_index"),
        content_potential_index=payload.get("content_potential_index"),
        utility_score=payload.get("utility_score"),
        in_stock=payload.get("in_stock", True),
        product_url=product_url,
        affiliate_url=affiliate_url,
        image_url=payload.get("image_url"),
        data_verification_map=verification_map,
        data_source=payload.get("data_source", "MANUAL_VERIFIED"),
        is_synthetic_test=bool(payload.get("is_synthetic_test", False)),
        is_active=bool(payload.get("is_active", True)),
    )

    score_and_update_product(db, product)
    db.add(product)
    db.flush()

    if affiliate_url:
        create_tracked_link(db, product, affiliate_url, utm_source="union_money_ai")

    db.add(
        AuditLog(
            actor="operator",
            action="CREATE_PRODUCT",
            entity_type="Product",
            entity_id=str(product.id),
            details={
                "title": product.title,
                "opportunity_score": product.opportunity_score,
                "classification": product.score_classification,
                "is_synthetic_test": product.is_synthetic_test,
            },
        )
    )
    db.commit()
    db.refresh(product)
    return product


def get_product_by_id(db: Session, product_id: int) -> Optional[Product]:
    """Busca um produto pelo ID."""
    return db.query(Product).filter(Product.id == product_id).first()


def list_products(
    db: Session,
    include_synthetic: bool = False,
    only_active: bool = True,
    marketplace_id: Optional[int] = None,
    category_id: Optional[int] = None,
) -> List[Product]:
    """Lista produtos com filtros opcionais."""
    query = db.query(Product)
    if only_active:
        query = query.filter(Product.is_active.is_(True))
    if not include_synthetic:
        query = query.filter(Product.is_synthetic_test.is_(False))
    if marketplace_id is not None:
        query = query.filter(Product.marketplace_id == marketplace_id)
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    return query.order_by(Product.created_at.desc()).all()


def update_product(db: Session, product_id: int, updates: Dict[str, Any]) -> Product:
    """Atualiza campos de um produto existente e recalcula seu Product Opportunity Score."""
    product = get_product_by_id(db, product_id)
    if not product:
        raise ValueError(f"Produto {product_id} não encontrado.")

    mutable_fields = (
        "title",
        "description",
        "marketplace_id",
        "category_id",
        "price",
        "original_price",
        "announced_commission_rate",
        "effective_commission_rate",
        "rating",
        "review_count",
        "seller_reputation",
        "demand_index",
        "competition_index",
        "content_potential_index",
        "utility_score",
        "in_stock",
        "product_url",
        "affiliate_url",
        "image_url",
        "data_verification_map",
        "is_active",
    )
    for field in mutable_fields:
        if field in updates:
            setattr(product, field, updates[field])

    if product.original_price and product.price and product.original_price > product.price > 0:
        product.discount_pct = round(
            ((product.original_price - product.price) / product.original_price) * 100.0, 2
        )
    else:
        product.discount_pct = 0.0

    score_and_update_product(db, product)

    db.add(
        AuditLog(
            actor="operator",
            action="UPDATE_PRODUCT",
            entity_type="Product",
            entity_id=str(product.id),
            details={"updated_fields": list(updates.keys()), "new_score": product.opportunity_score},
        )
    )
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: int, hard_delete: bool = False) -> bool:
    """Desativa (soft delete) ou remove um produto."""
    product = get_product_by_id(db, product_id)
    if not product:
        return False

    if hard_delete:
        db.delete(product)
    else:
        product.is_active = False

    db.add(
        AuditLog(
            actor="operator",
            action="DELETE_PRODUCT",
            entity_type="Product",
            entity_id=str(product_id),
            details={"hard_delete": hard_delete},
        )
    )
    db.commit()
    return True

