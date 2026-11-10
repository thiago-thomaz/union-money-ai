"""UNION LINK MANAGER — Gestor de Links de Afiliados e Registro Auditável de Cliques (Seção 7).

Funções:
- Gerar identificadores internos únicos (short_code).
- Relacionar produtos a links de afiliados preservando parâmetros de atribuição originais.
- Armazenar marketplace de origem, canal de divulgação e campanha.
- Verificar validade sintática e de domínio quando permitido.
- Registrar cliques próprios no site filtrando bots (nunca tratando cliques como vendas).
- Gerar relatórios detalhados por link.
"""

from datetime import datetime, timezone
import secrets
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.security import fingerprint_visitor, is_suspected_bot
from app.models.affiliate import AffiliateLink
from app.models.click import ClickLog
from app.models.conversion import Conversion
from app.models.marketplace import Marketplace
from app.models.product import Product

ALLOWED_AFFILIATE_DOMAINS = (
    "mercadolivre.com.br",
    "mercadolivre.com",
    "produto.mercadolivre.com.br",
    "amazon.com.br",
    "amzn.to",
    "shopee.com.br",
    "s.shopee.com.br",
    "shp.ee",
)


class UnionLinkManager:
    """Gestor oficial de links de afiliados do UNION MONEY AI."""

    @staticmethod
    def validate_affiliate_url_format(url: str) -> Tuple[bool, str]:
        """Verifica se a URL utiliza HTTPS e pertence a um domínio oficial autorizado."""
        if not url or not url.strip():
            return False, "URL vazia."
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("https", "http"):
            return False, "Protocolo inválido (exigido https)."
        host = (parsed.netloc or "").lower().split(":")[0]
        if not host:
            return False, "Domínio ausente."
        if any(host == dom or host.endswith("." + dom) for dom in ALLOWED_AFFILIATE_DOMAINS):
            return True, "Domínio de marketplace oficial verificado."
        return False, f"Domínio '{host}' fora da lista de marketplaces oficiais."

    @classmethod
    def verify_link_validity(cls, db: Session, link: AffiliateLink) -> Dict[str, Any]:
        """Valida sintaxe, domínio e disponibilidade do produto associado ao link."""
        is_valid_url, reason = cls.validate_affiliate_url_format(link.affiliate_url)
        product = db.query(Product).filter(Product.id == link.product_id).first()
        product_available = bool(product and product.is_active and product.in_stock)

        now_utc = datetime.now(timezone.utc)
        link.last_verified_at = now_utc

        if is_valid_url and product_available:
            link.validity_status = "VALID"
            link.is_verified = True
            link.is_active = True
        else:
            link.validity_status = "INVALID" if not is_valid_url else "PRODUCT_UNAVAILABLE"
            link.is_active = False

        db.commit()
        db.refresh(link)
        return {
            "link_id": link.id,
            "short_code": link.short_code,
            "validity_status": link.validity_status,
            "is_active": link.is_active,
            "reason": reason if is_valid_url else f"Link pausado: {reason}",
        }

    @classmethod
    def review_all_links(cls, db: Session) -> Dict[str, int]:
        """Revisa todos os links cadastrados e pausa links inválidos ou de produtos indisponíveis."""
        links = db.query(AffiliateLink).all()
        valid_count = 0
        paused_count = 0
        for link in links:
            res = cls.verify_link_validity(db, link)
            if res["is_active"]:
                valid_count += 1
            else:
                paused_count += 1
        return {
            "total_reviewed": len(links),
            "valid_active": valid_count,
            "paused_or_invalid": paused_count,
        }

    @staticmethod
    def has_official_affiliate_attribution(url: str, marketplace_slug: str) -> bool:
        """Verifica se o link possui parâmetros reais de atribuição de afiliado da plataforma (não aceita falso link)."""
        u = (url or "").strip().lower()
        slug = (marketplace_slug or "").strip().lower()
        if not u:
            return False
        if slug == "mercadolivre":
            return "/sec/" in u or "matt_tool=" in u or "matt_word=" in u
        if slug == "amazon":
            return "tag=" in u or "amzn.to/" in u
        if slug == "shopee":
            return "s.shopee.com.br/" in u or "shp.ee/" in u or "af_siteid=" in u or "utm_source=an_affiliate" in u
        return "/sec/" in u or "tag=" in u or "s.shopee.com.br/" in u

    @classmethod
    def auto_generate_or_update_link_for_product(
        cls,
        db: Session,
        product: Product,
        campaign_id: Optional[int] = None,
        channel: str = "SITE",
    ) -> Dict[str, Any]:
        """Gera ou atualiza automaticamente o link rastreável consultando o conector oficial do marketplace (Seção 5)."""
        from app.intelligence.discovery import get_connector

        mp = db.query(Marketplace).filter(Marketplace.id == product.marketplace_id).first()
        mp_slug = mp.slug if mp else "mercadolivre"
        connector = get_connector(mp_slug)

        base_url = (product.affiliate_url or product.product_url or "").strip()
        generated_url = connector.build_affiliate_link(base_url)
        is_valid_domain, domain_msg = cls.validate_affiliate_url_format(generated_url)
        has_real_attribution = cls.has_official_affiliate_attribution(generated_url, mp_slug)

        if has_real_attribution and is_valid_domain:
            product.affiliate_url = generated_url
            validity = "VALID"
        elif is_valid_domain:
            # Não cria link que apenas aparente ser link de afiliado sem autorização/tag real
            validity = "AUTHORIZATION_REQUIRED"
        else:
            validity = "INVALID"

        existing_link = (
            db.query(AffiliateLink)
            .filter(
                AffiliateLink.product_id == product.id,
                AffiliateLink.channel == channel.upper().strip(),
            )
            .first()
        )
        now_utc = datetime.now(timezone.utc)
        if existing_link:
            existing_link.affiliate_url = generated_url
            existing_link.campaign_id = campaign_id or existing_link.campaign_id
            existing_link.validity_status = validity
            existing_link.is_verified = validity == "VALID"
            existing_link.last_verified_at = now_utc
            db.commit()
            db.refresh(existing_link)
            link_obj = existing_link
        else:
            link_obj = create_tracked_link(
                db=db,
                product=product,
                affiliate_url=generated_url,
                utm_source="union_money_ai",
                utm_medium=channel.lower(),
                utm_campaign=f"camp_{campaign_id}" if campaign_id else "auto",
                channel=channel,
                campaign_id=campaign_id,
            )
            link_obj.validity_status = validity
            link_obj.is_verified = validity == "VALID"
            db.commit()
            db.refresh(link_obj)

        return {
            "link_id": link_obj.id,
            "short_code": link_obj.short_code,
            "internal_tracking_url": f"/r/{link_obj.short_code}",
            "affiliate_url": link_obj.affiliate_url,
            "has_official_affiliate_attribution": has_real_attribution,
            "validity_status": link_obj.validity_status,
            "marketplace_slug": mp_slug,
            "campaign_id": link_obj.campaign_id,
            "reason": domain_msg,
        }

    @classmethod
    def get_link_reports(cls, db: Session) -> List[Dict[str, Any]]:
        """Gera relatório consolidado de desempenho por link de afiliado."""
        links = db.query(AffiliateLink).order_by(AffiliateLink.created_at.desc()).all()
        reports: List[Dict[str, Any]] = []
        for link in links:
            prod = db.query(Product).filter(Product.id == link.product_id).first()
            mp = db.query(Marketplace).filter(Marketplace.id == link.marketplace_id).first()
            human_clicks = (
                db.query(func.count(ClickLog.id))
                .filter(ClickLog.affiliate_link_id == link.id, ClickLog.is_valid_human.is_(True))
                .scalar()
                or 0
            )
            conversions = (
                db.query(func.count(Conversion.id))
                .filter(Conversion.product_id == link.product_id, Conversion.status == "CONFIRMED")
                .scalar()
                or 0
            )
            reports.append(
                {
                    "link_id": link.id,
                    "short_code": link.short_code,
                    "internal_path": f"/r/{link.short_code}",
                    "product_id": link.product_id,
                    "product_title": prod.title if prod else "N/D",
                    "marketplace": mp.name if mp else "N/D",
                    "channel": link.channel,
                    "campaign_id": link.campaign_id,
                    "affiliate_url": link.affiliate_url,
                    "validity_status": link.validity_status,
                    "is_active": link.is_active,
                    "human_clicks": human_clicks,
                    "confirmed_conversions": conversions,
                }
            )
        return reports


def create_tracked_link(
    db: Session,
    product: Product,
    affiliate_url: str,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    channel: str = "SITE",
    campaign_id: Optional[int] = None,
) -> AffiliateLink:
    """Cria um link rastreável interno vinculado ao produto, canal e campanha sem alterar a atribuição do marketplace."""
    short_code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10]
    while db.query(AffiliateLink).filter(AffiliateLink.short_code == short_code).first():
        short_code = secrets.token_urlsafe(6)[:10]

    is_valid, _ = UnionLinkManager.validate_affiliate_url_format(affiliate_url)

    link = AffiliateLink(
        product_id=product.id,
        marketplace_id=product.marketplace_id,
        campaign_id=campaign_id,
        channel=channel.upper().strip(),
        short_code=short_code,
        original_product_url=product.product_url,
        affiliate_url=affiliate_url.strip(),
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        validity_status="VALID" if is_valid else "UNVERIFIED",
        last_verified_at=datetime.now(timezone.utc),
        is_verified=is_valid,
        is_active=True,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def register_link_click(
    db: Session,
    short_code: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    channel: str = "DIRECT",
    referrer: Optional[str] = None,
) -> Tuple[Optional[AffiliateLink], Optional[ClickLog]]:
    """Resolve um short_code e registra clique real se não for bot. Cliques NUNCA são vendas."""
    link = (
        db.query(AffiliateLink)
        .filter(AffiliateLink.short_code == short_code, AffiliateLink.is_active.is_(True))
        .first()
    )
    if not link:
        return None, None

    is_human = not is_suspected_bot(user_agent)
    fp = fingerprint_visitor(ip_address, user_agent)

    existing = (
        db.query(ClickLog)
        .filter(
            ClickLog.affiliate_link_id == link.id,
            ClickLog.visitor_fingerprint == fp,
            ClickLog.is_valid_human.is_(True),
        )
        .first()
    )
    if existing and is_human:
        return link, existing

    click_log = ClickLog(
        affiliate_link_id=link.id,
        product_id=link.product_id,
        marketplace_id=link.marketplace_id,
        campaign_id=link.campaign_id,
        channel=channel or link.channel,
        visitor_fingerprint=fp,
        referrer=referrer,
        is_valid_human=is_human,
    )
    db.add(click_log)
    db.commit()
    db.refresh(click_log)
    return link, click_log
