"""UNION DISTRIBUTION ENGINE & Fila Editorial (Seção 8).

Estados da Fila Editorial:
- RASCUNHO
- EM_REVISAO
- APROVADO
- AGENDADO
- PUBLICADO
- FALHOU
- ARQUIVADO

Regras:
- Controle de duplicidade por hash (dedup_hash).
- Bloqueio automático de conteúdos abaixo do Content Quality Score mínimo.
- Não simula publicação em redes sociais sem credenciais; gera pacote verificável para postagem manual.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.content_engine.seo import slugify
from app.integrations.social.instagram import InstagramConnector
from app.integrations.social.pinterest import PinterestConnector
from app.integrations.social.youtube import YouTubeConnector
from app.marketing.landing_pages import build_product_landing_page
from app.models.autopilot import EditorialQueueItem, EditorialState
from app.models.content import ContentItem
from app.models.marketplace import Marketplace
from app.models.product import Product
from app.models.publication import Publication

SOCIAL_CONNECTORS = {
    "YOUTUBE": YouTubeConnector(),
    "INSTAGRAM": InstagramConnector(),
    "PINTEREST": PinterestConnector(),
}


def compute_editorial_dedup_hash(product_id: int, content_id: Optional[int], channel: str, title: str) -> str:
    raw = f"{product_id}|{content_id or 0}|{channel.upper().strip()}|{slugify(title)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


class UnionDistributionEngine:
    """Motor de distribuição multicanal com fila editorial auditável."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue_editorial_item(
        self,
        product: Product,
        content: ContentItem,
        target_channel: str = "SITE",
        require_human_approval: bool = False,
        campaign_id: Optional[int] = None,
        target_keyword: Optional[str] = None,
    ) -> EditorialQueueItem:
        """Adiciona um conteúdo à fila editorial evitando duplicidade."""
        ch_upper = target_channel.upper().strip()
        dedup = compute_editorial_dedup_hash(product.id, content.id, ch_upper, content.title)

        existing = (
            self.db.query(EditorialQueueItem)
            .filter(EditorialQueueItem.dedup_hash == dedup)
            .first()
        )
        if existing:
            return existing

        min_score = settings.MIN_CONTENT_QUALITY_SCORE
        if content.quality_score < min_score:
            initial_state = EditorialState.RASCUNHO
        elif require_human_approval:
            initial_state = EditorialState.EM_REVISAO
        else:
            initial_state = EditorialState.APROVADO

        item = EditorialQueueItem(
            product_id=product.id,
            content_id=content.id,
            campaign_id=campaign_id or content.campaign_id,
            title=content.title,
            content_format=content.content_type,
            target_channel=ch_upper,
            target_keyword=target_keyword or content.seo_keywords,
            quality_score=content.quality_score,
            require_human_approval=require_human_approval,
            state=initial_state,
            dedup_hash=dedup,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def transition_state(self, queue_id: int, new_state: str) -> EditorialQueueItem:
        """Transiciona o estado de um item da fila editorial (ex.: EM_REVISAO -> APROVADO)."""
        item = self.db.query(EditorialQueueItem).filter(EditorialQueueItem.id == queue_id).first()
        if not item:
            raise ValueError(f"Item de fila editorial #{queue_id} não encontrado.")
        valid_states = {
            EditorialState.RASCUNHO,
            EditorialState.EM_REVISAO,
            EditorialState.APROVADO,
            EditorialState.AGENDADO,
            EditorialState.PUBLICADO,
            EditorialState.FALHOU,
            EditorialState.ARQUIVADO,
        }
        st_upper = new_state.upper().strip()
        if st_upper not in valid_states:
            raise ValueError(f"Estado editorial inválido: {new_state}")
        item.state = st_upper
        self.db.commit()
        self.db.refresh(item)
        return item

    def publish_queue_item(self, queue_id: int) -> Dict[str, Any]:
        """Publica um item aprovado da fila editorial ou gera pacote de exportação manual."""
        item = self.db.query(EditorialQueueItem).filter(EditorialQueueItem.id == queue_id).first()
        if not item:
            raise ValueError(f"Item da fila #{queue_id} não encontrado.")

        if item.quality_score < settings.MIN_CONTENT_QUALITY_SCORE:
            item.state = EditorialState.FALHOU
            item.error_details = (
                f"Bloqueado: Content Quality Score ({item.quality_score}) abaixo do mínimo ({settings.MIN_CONTENT_QUALITY_SCORE})."
            )
            self.db.commit()
            return {
                "queue_id": item.id,
                "state": item.state,
                "published": False,
                "reason": item.error_details,
            }

        if item.require_human_approval and item.state not in (EditorialState.APROVADO, EditorialState.AGENDADO):
            return {
                "queue_id": item.id,
                "state": item.state,
                "published": False,
                "reason": "Aguardando aprovação humana explícita.",
            }

        content = self.db.query(ContentItem).filter(ContentItem.id == item.content_id).first()
        product = self.db.query(Product).filter(Product.id == item.product_id).first()
        if not content or not product:
            item.state = EditorialState.FALHOU
            item.error_details = "Conteúdo ou produto associado não encontrado."
            self.db.commit()
            return {"queue_id": item.id, "state": item.state, "published": False, "reason": item.error_details}

        channel = item.target_channel.upper().strip()
        now_utc = datetime.now(timezone.utc)

        if channel in ("SITE", "LANDING_PAGE", "UNION_OFERTAS"):
            mp = self.db.query(Marketplace).filter(Marketplace.id == product.marketplace_id).first()
            lp_path = build_product_landing_page(
                product=product,
                marketplace_name=mp.name if mp else "Marketplace",
                tracked_url=product.affiliate_url or product.product_url,
            )
            site_url = f"/ofertas/artigos/{content.slug}"
            pub = Publication(
                content_id=content.id,
                product_id=product.id,
                campaign_id=item.campaign_id,
                channel=channel,
                external_post_id=f"site-{content.id}",
                published_url=site_url,
                status="PUBLISHED",
                published_at=now_utc,
            )
            content.status = "PUBLISHED"
            item.state = EditorialState.PUBLICADO
            item.published_url = site_url
            item.package_path = str(lp_path)
            item.published_at = now_utc
            self.db.add(pub)
            self.db.commit()
            self.db.refresh(pub)
            return {
                "queue_id": item.id,
                "publication_id": pub.id,
                "state": item.state,
                "publication_status": pub.status,
                "published_url": site_url,
                "landing_page_path": str(lp_path),
            }

        # Canais sociais (YouTube, Instagram, Pinterest)
        connector = SOCIAL_CONNECTORS.get(channel)
        dispatch_info = (
            connector.publish_or_export(content.title, content.body, content.media_path)
            if connector
            else {"channel": channel, "status": "EXPORTED_FOR_MANUAL"}
        )

        # Gera arquivo de pacote pronto para publicação manual quando sem API automática
        pkg_file = settings.storage_dir / "publications" / f"pacote-{channel.lower()}-{content.id}.json"
        pkg_payload = {
            "channel": channel,
            "product_id": product.id,
            "product_title": product.title,
            "content_id": content.id,
            "title": content.title,
            "body": content.body,
            "call_to_action": content.call_to_action,
            "media_path": content.media_path,
            "subtitle_path": content.subtitle_path,
            "affiliate_url": product.affiliate_url or product.product_url,
            "generated_at": now_utc.isoformat(),
            "dispatch_status": dispatch_info.get("status"),
        }
        pkg_file.write_text(json.dumps(pkg_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        pub_status = dispatch_info.get("status", "EXPORTED_FOR_MANUAL")
        pub = Publication(
            content_id=content.id,
            product_id=product.id,
            campaign_id=item.campaign_id,
            channel=channel,
            published_url=str(pkg_file),
            status=pub_status,
            published_at=now_utc,
        )
        content.status = "PUBLISHED"
        item.state = EditorialState.PUBLICADO
        item.package_path = str(pkg_file)
        item.published_url = str(pkg_file)
        item.published_at = now_utc
        self.db.add(pub)
        self.db.commit()
        self.db.refresh(pub)
        return {
            "queue_id": item.id,
            "publication_id": pub.id,
            "state": item.state,
            "publication_status": pub.status,
            "package_path": str(pkg_file),
        }


def distribute_content(
    db: Session,
    content: ContentItem,
    channel: str,
    published_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Função compatível com a Parte 1 integrada ao UnionDistributionEngine."""
    product = db.query(Product).filter(Product.id == content.product_id).first()
    if not product:
        raise ValueError("Produto associado ao conteúdo não encontrado.")

    engine = UnionDistributionEngine(db)
    q_item = engine.enqueue_editorial_item(
        product=product,
        content=content,
        target_channel=channel,
        require_human_approval=False,
    )
    if q_item.state != EditorialState.PUBLICADO:
        res = engine.publish_queue_item(q_item.id)
        pub_id = res.get("publication_id")
        status = res.get("publication_status", res.get("state", "PUBLISHED"))
    else:
        pub = db.query(Publication).filter(Publication.content_id == content.id).first()
        pub_id = pub.id if pub else None
        status = pub.status if pub else "PUBLISHED"

    if published_url and pub_id:
        pub_obj = db.query(Publication).filter(Publication.id == pub_id).first()
        if pub_obj:
            pub_obj.published_url = published_url
            db.commit()

    return {
        "publication_id": pub_id,
        "queue_id": q_item.id,
        "channel": channel.upper().strip(),
        "status": status,
        "dispatch_details": {"queue_state": q_item.state, "package_path": q_item.package_path},
    }
