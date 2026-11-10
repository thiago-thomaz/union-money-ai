"""Descoberta Automática e Incremental de Produtos sem Cadastro Manual (Seção 4).

Fluxo de 12 Etapas:
1. Consultar automaticamente fontes autorizadas.
2. Buscar produtos elegíveis.
3. Identificar categoria automaticamente por taxonomia.
4. Obter informações disponíveis.
5. Verificar preços (> 0).
6. Verificar disponibilidade (in_stock).
7. Obter comissão aplicável (nunca tratando comissão estimada como comissão garantida).
8. Calcular pontuação comercial (ProductOpportunityScorer).
9. Comparar oportunidades.
10. Registrar os produtos no banco (incremental, sem duplicidade e exigindo dados mínimos verificáveis).
11. Atualizar produtos existentes.
12. Remover ou suspender ofertas inválidas ou que deixaram de ser interessantes.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.config import settings
from app.intelligence.discovery import CONNECTOR_REGISTRY, discover_from_marketplace
from app.intelligence.opportunity import score_and_update_product
from app.marketing.link_manager import UnionLinkManager
from app.models.click import ClickLog
from app.models.conversion import Conversion
from app.models.marketplace import Category, Marketplace
from app.models.product import Product


CATEGORY_KEYWORDS_TAXONOMY: Dict[str, List[str]] = {
    "eletronicos-e-smartphones": ["smartphone", "celular", "fone", "bluetooth", "tv", "caixa de som", "smartwatch", "tablet"],
    "informatica-e-acessorios": ["notebook", "monitor", "ssd", "teclado", "mouse", "placa", "roteador", "webcam", "impressora"],
    "eletrodomesticos-e-airfryer": ["airfryer", "fritadeira", "cafeteira", "liquidificador", "aspirador", "micro-ondas", "geladeira"],
    "casa-cozinha-e-organizacao": ["panela", "faqueiro", "organizador", "lampada", "fechadura", "purificador", "garrafa termica"],
    "beleza-e-cuidados-pessoais": ["secador", "chapinha", "barbeador", "perfume", "hidratante", "skincare", "escova"],
    "saude-suplementos-e-bem-estar": ["whey", "creatina", "vitamina", "balanca", "massageador", "oximetro"],
    "esporte-fitness-e-lazer": ["bicicleta", "esteira", "halter", "barraca", "mochila", "tenis corrida"],
    "ferramentas-e-construcao": ["parafusadeira", "furadeira", "chave", "serra", "trena", "lavadora de alta pressao"],
    "games-e-consoles": ["playstation", "xbox", "nintendo", "controle", "headset gamer", "cadeira gamer"],
    "pet-shop-e-acessorios": ["racao", "comedouro", "arranhador", "coleira", "caminha pet", "antipulgas"],
}


class AutonomousProductDiscovery:
    """Motor contínuo e incremental de descoberta, atualização e higienização de catálogo."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def identify_category_automatically(self, title: str, description: Optional[str] = None) -> Category:
        """Identifica automaticamente a categoria ideal com base em taxonomia de palavras-chave."""
        text_blob = f"{title or ''} {description or ''}".lower()
        categories = self.db.query(Category).filter(Category.is_active.is_(True)).all()
        cat_by_slug = {c.slug: c for c in categories}

        best_slug = "eletronicos-e-smartphones"
        best_hits = 0
        for slug, keywords in CATEGORY_KEYWORDS_TAXONOMY.items():
            hits = sum(1 for kw in keywords if kw in text_blob)
            if hits > best_hits and slug in cat_by_slug:
                best_hits = hits
                best_slug = slug

        return cat_by_slug.get(best_slug) or categories[0]

    @staticmethod
    def has_minimum_verifiable_info(raw_item: Dict[str, Any]) -> bool:
        """Garante que produtos sem informações mínimas verificáveis (título, preço > 0, URL oficial) sejam rejeitados."""
        title = str(raw_item.get("title") or "").strip()
        price = float(raw_item.get("price") or 0.0)
        url = str(raw_item.get("product_url") or raw_item.get("affiliate_url") or "").strip()
        if len(title) < 5 or price <= 0.0 or not url.startswith("http"):
            return False
        valid_domain, _ = UnionLinkManager.validate_affiliate_url_format(url)
        return valid_domain

    def ingest_authorized_items_incrementally(
        self,
        items: List[Dict[str, Any]],
        marketplace_slug: str,
        is_synthetic_test: bool = False,
    ) -> Dict[str, Any]:
        """Executa descoberta incremental: cadastra novos produtos elegíveis, atualiza existentes e gera links."""
        mkt = (
            self.db.query(Marketplace)
            .filter(Marketplace.slug == marketplace_slug.lower().strip())
            .first()
        )
        if not mkt:
            raise ValueError(f"Marketplace '{marketplace_slug}' não encontrado.")

        created_ids: List[int] = []
        updated_ids: List[int] = []
        rejected_invalid_count = 0
        links_processed = 0

        for raw in items:
            if not self.has_minimum_verifiable_info(raw):
                rejected_invalid_count += 1
                continue

            ext_id = str(raw.get("external_id") or "").strip() or None
            prod_url = str(raw.get("product_url") or "").strip()
            title = str(raw.get("title") or "").strip()
            price = round(float(raw.get("price") or 0.0), 2)
            orig_price_raw = raw.get("original_price")
            orig_price = round(float(orig_price_raw), 2) if orig_price_raw else None
            in_stock = bool(raw.get("in_stock", True))

            cat = self.identify_category_automatically(title, raw.get("description"))

            # Comissão anunciada vs estimada (nunca tratada como garantida)
            comm_rate = float(
                raw.get("announced_commission_rate")
                or mkt.default_commission_rate
                or cat.default_commission_estimate
                or 7.0
            )

            existing: Optional[Product] = None
            if ext_id:
                existing = (
                    self.db.query(Product)
                    .filter(Product.marketplace_id == mkt.id, Product.external_id == ext_id)
                    .first()
                )
            if not existing and prod_url:
                existing = (
                    self.db.query(Product)
                    .filter(Product.marketplace_id == mkt.id, Product.product_url == prod_url)
                    .first()
                )

            if existing:
                existing.title = title
                existing.price = price
                existing.original_price = orig_price
                existing.in_stock = in_stock
                existing.announced_commission_rate = comm_rate
                if raw.get("rating") is not None:
                    existing.rating = float(raw["rating"])
                if raw.get("review_count") is not None:
                    existing.review_count = int(raw["review_count"])
                if raw.get("affiliate_url"):
                    existing.affiliate_url = str(raw["affiliate_url"]).strip()
                score_and_update_product(self.db, existing)
                if settings.AUTO_AFFILIATE_LINKS:
                    UnionLinkManager.auto_generate_or_update_link_for_product(self.db, existing)
                    links_processed += 1
                updated_ids.append(existing.id)
            else:
                new_prod = Product(
                    marketplace_id=mkt.id,
                    category_id=cat.id,
                    external_id=ext_id,
                    title=title,
                    description=raw.get("description"),
                    price=price,
                    original_price=orig_price,
                    currency="BRL",
                    in_stock=in_stock,
                    rating=float(raw["rating"]) if raw.get("rating") is not None else None,
                    review_count=int(raw["review_count"]) if raw.get("review_count") is not None else None,
                    demand_index=float(raw.get("demand_index") or 75.0),
                    competition_index=float(raw.get("competition_index") or 50.0),
                    content_potential_index=float(raw.get("content_potential_index") or 80.0),
                    announced_commission_rate=comm_rate,
                    estimated_commission_value=round(price * (comm_rate / 100.0), 2),
                    product_url=prod_url,
                    affiliate_url=str(raw.get("affiliate_url") or prod_url).strip(),
                    image_url=raw.get("image_url"),
                    data_source=str(raw.get("data_source") or "OFFICIAL_API"),
                    is_synthetic_test=bool(raw.get("is_synthetic_test", is_synthetic_test)),
                    is_active=in_stock,
                )
                self.db.add(new_prod)
                self.db.flush()
                score_and_update_product(self.db, new_prod)
                if settings.AUTO_AFFILIATE_LINKS:
                    UnionLinkManager.auto_generate_or_update_link_for_product(self.db, new_prod)
                    links_processed += 1
                created_ids.append(new_prod.id)

        self.db.commit()
        return {
            "marketplace_slug": mkt.slug,
            "created_count": len(created_ids),
            "created_product_ids": created_ids,
            "updated_count": len(updated_ids),
            "updated_product_ids": updated_ids,
            "rejected_invalid_count": rejected_invalid_count,
            "links_processed": links_processed,
            "estimated_commission_is_guaranteed": False,
        }

    def suspend_invalid_or_uninteresting_products(
        self,
        min_acceptable_score: float = 40.0,
        max_clicks_without_conversion: int = 80,
    ) -> Dict[str, Any]:
        """Suspende ofertas sem estoque, com link inválido ou que deixaram de ser comercialmente interessantes."""
        active_products = self.db.query(Product).filter(Product.is_active.is_(True)).all()
        suspended_out_of_stock: List[int] = []
        suspended_low_score: List[int] = []
        suspended_poor_conversion: List[int] = []

        for prod in active_products:
            score_and_update_product(self.db, prod)
            if not prod.in_stock or prod.price <= 0:
                prod.is_active = False
                suspended_out_of_stock.append(prod.id)
                continue

            if prod.opportunity_score is not None and prod.opportunity_score < min_acceptable_score:
                prod.is_active = False
                suspended_low_score.append(prod.id)
                continue

            clicks_count = (
                self.db.query(func.count(ClickLog.id))
                .filter(ClickLog.product_id == prod.id, ClickLog.is_valid_human.is_(True))
                .scalar()
                or 0
            )
            convs_count = (
                self.db.query(func.count(Conversion.id))
                .filter(Conversion.product_id == prod.id, Conversion.status == "CONFIRMED")
                .scalar()
                or 0
            )
            if clicks_count >= max_clicks_without_conversion and convs_count == 0:
                prod.is_active = False
                suspended_poor_conversion.append(prod.id)

        self.db.commit()
        return {
            "checked_count": len(active_products),
            "suspended_out_of_stock_ids": suspended_out_of_stock,
            "suspended_low_score_ids": suspended_low_score,
            "suspended_poor_conversion_ids": suspended_poor_conversion,
            "total_suspended": len(suspended_out_of_stock) + len(suspended_low_score) + len(suspended_poor_conversion),
        }

    def run_continuous_discovery_cycle(self, queries: Optional[List[str]] = None, limit_per_query: int = 10) -> Dict[str, Any]:
        """Executa o fluxo completo de 12 etapas em todas as fontes autorizadas e reavalia o catálogo existente."""
        search_terms = queries or ["smartphone", "notebook", "airfryer", "fone bluetooth", "monitor"]
        connectors_summary: Dict[str, Any] = {}
        total_created = 0
        total_updated = 0

        for slug in CONNECTOR_REGISTRY:
            slug_created = 0
            slug_updated = 0
            last_status = "AUTHORIZATION_REQUIRED"
            for q in search_terms[:2]:
                disc = discover_from_marketplace(self.db, slug, query=q, limit=limit_per_query)
                last_status = disc["status"]
                if disc["status"] == "SUCCESS" and disc["items"]:
                    ing = self.ingest_authorized_items_incrementally(disc["items"], marketplace_slug=slug)
                    slug_created += ing["created_count"]
                    slug_updated += ing["updated_count"]
                else:
                    break
            total_created += slug_created
            total_updated += slug_updated
            connectors_summary[slug] = {
                "status": last_status,
                "created": slug_created,
                "updated": slug_updated,
            }

        cleanup = self.suspend_invalid_or_uninteresting_products()
        ranked = (
            self.db.query(Product)
            .filter(Product.is_active.is_(True), Product.in_stock.is_(True), Product.is_synthetic_test.is_(False))
            .order_by(Product.opportunity_score.desc().nullslast())
            .limit(10)
            .all()
        )

        return {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "connectors_summary": connectors_summary,
            "total_created": total_created,
            "total_updated": total_updated,
            "catalog_cleanup": cleanup,
            "top_opportunities": [
                {
                    "product_id": p.id,
                    "title": p.title,
                    "price": p.price,
                    "opportunity_score": p.opportunity_score,
                    "estimated_commission_value": p.estimated_commission_value,
                    "is_guaranteed_commission": False,
                }
                for p in ranked
            ],
        }
