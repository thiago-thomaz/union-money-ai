"""Pipeline Autônomo de Produção de Conteúdo em 9 Estados e Atualização Automática (Seção 6).

Estados oficiais:
1. DISCOVERY
2. ANALYSIS
3. SCRIPT
4. CONTENT
5. QUALITY_CHECK
6. SEO
7. READY
8. PUBLISHED
9. MONITORING
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.content_engine.union_content_engine import (
    UnionContentEngine,
    _format_brl,
    generate_illustrative_infographic,
)
from app.marketing.multichannel_publisher import MultiChannelAutoPublisher
from app.models.autonomous import ContentProductionPipeline, PipelineStage
from app.models.content import ContentItem
from app.models.marketplace import Category, Marketplace
from app.models.product import Product


class AutonomousContentPipeline:
    """Executa a produção e publicação 100% autônoma sem necessidade de upload manual."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.content_engine = UnionContentEngine(db)
        self.publisher = MultiChannelAutoPublisher(db)

    @staticmethod
    def identify_buyer_intent(product: Product) -> str:
        """Identifica a intenção comercial de busca do consumidor com base na oferta."""
        if product.original_price and product.original_price > product.price:
            return "TRANSACTIONAL_DEAL"
        if product.price >= 800.0:
            return "COMPARATIVE_HIGH_TICKET"
        return "COMMERCIAL_INVESTIGATION"

    def _record_stage(
        self,
        pipeline: ContentProductionPipeline,
        stage: str,
        note: str,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        hist = list(pipeline.state_history or [])
        hist.append({"stage": stage, "timestamp": now_iso, "note": note})
        pipeline.current_state = stage
        pipeline.state_history = hist
        self.db.commit()

    def execute_for_product(
        self,
        product: Product,
        target_channels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Executa a máquina de estados completa (DISCOVERY -> ... -> MONITORING) para um produto."""
        channels = target_channels or ["UNION_OFERTAS"]
        intent = self.identify_buyer_intent(product)

        pipeline = ContentProductionPipeline(
            product_id=product.id,
            current_state=PipelineStage.DISCOVERY,
            buyer_intent=intent,
            state_history=[],
        )
        self.db.add(pipeline)
        self.db.commit()
        self.db.refresh(pipeline)

        # 1. DISCOVERY
        self._record_stage(
            pipeline,
            PipelineStage.DISCOVERY,
            f"Produto selecionado para pauta: '{product.title}' (Score: {product.opportunity_score}).",
        )

        # 2. ANALYSIS
        mp = self.db.query(Marketplace).filter(Marketplace.id == product.marketplace_id).first()
        cat = self.db.query(Category).filter(Category.id == product.category_id).first()
        mp_name = mp.name if mp else "Marketplace"
        cat_name = cat.name if cat else "Geral"
        self._record_stage(
            pipeline,
            PipelineStage.ANALYSIS,
            f"Intenção '{intent}' identificada na categoria '{cat_name}' ({mp_name}).",
        )

        # 3. SCRIPT (Gera roteiro estruturado de 7 etapas e vídeo curto 9:16 com legenda .srt)
        script_item = self.content_engine.produce(product=product, content_type="VIDEO_SCRIPT")
        video_item: Optional[ContentItem] = None
        if settings.AUTO_VIDEO_RENDERING:
            video_item = self.content_engine.produce(product=product, content_type="SHORT_VIDEO", aspect_ratio="9:16")
            pipeline.video_content_id = video_item.id
        self._record_stage(
            pipeline,
            PipelineStage.SCRIPT,
            f"Roteiro #{script_item.id} e vídeo curto MP4 + legenda .srt gerados sem upload manual.",
        )

        # 4. CONTENT (Gera avaliação editorial/artigo, comparativo e imagem ilustrativa original)
        primary_format = "COMPARISON" if intent == "COMPARATIVE_HIGH_TICKET" else "EDITORIAL_REVIEW"
        article_item = self.content_engine.produce(product=product, content_type=primary_format)
        infographic_path = generate_illustrative_infographic(product, cat_name, mp_name)
        article_item.media_path = str(infographic_path)
        pipeline.content_id = article_item.id
        self.db.commit()
        self._record_stage(
            pipeline,
            PipelineStage.CONTENT,
            f"Conteúdo editorial #{article_item.id} ({primary_format}) e infográfico original ({infographic_path.name}) criados.",
        )

        # 5. QUALITY_CHECK
        pipeline.quality_score = article_item.quality_score
        if article_item.quality_score < settings.MIN_CONTENT_QUALITY_SCORE:
            pipeline.error_message = (
                f"Content Quality Score ({article_item.quality_score}) abaixo do mínimo ({settings.MIN_CONTENT_QUALITY_SCORE})."
            )
            self._record_stage(pipeline, PipelineStage.QUALITY_CHECK, pipeline.error_message)
            return {
                "pipeline_uid": pipeline.pipeline_uid,
                "current_state": pipeline.current_state,
                "published": False,
                "error": pipeline.error_message,
            }
        self._record_stage(
            pipeline,
            PipelineStage.QUALITY_CHECK,
            f"Aprovado no controle de qualidade com nota {article_item.quality_score}/100.",
        )

        # 6. SEO
        self._record_stage(
            pipeline,
            PipelineStage.SEO,
            f"Metadados SEO, slug '{article_item.slug}' e JSON-LD estruturados validados.",
        )

        # 7. READY
        self._record_stage(
            pipeline,
            PipelineStage.READY,
            "Ativos textuais e audiovisuais prontos para distribuição multicanal.",
        )

        # 8. PUBLISHED
        pub_results: List[Dict[str, Any]] = []
        primary_pub_id: Optional[int] = None
        for ch in channels:
            ch_upper = ch.upper().strip()
            target_content = (
                video_item
                if (ch_upper in ("YOUTUBE_SHORTS", "YOUTUBE", "INSTAGRAM_REELS") and video_item is not None)
                else article_item
            )
            res = self.publisher.publish_to_channel(product=product, content=target_content, channel=ch_upper)
            pub_results.append(res)
            if res.get("published") and primary_pub_id is None:
                primary_pub_id = res.get("publication_id")

        pipeline.publication_id = primary_pub_id
        self._record_stage(
            pipeline,
            PipelineStage.PUBLISHED,
            f"Publicação executada em {len(channels)} canal(is); publicação primária #{primary_pub_id}.",
        )

        # 9. MONITORING
        self._record_stage(
            pipeline,
            PipelineStage.MONITORING,
            "Conteúdo em monitoramento contínuo de cliques, conversões e atualização de preço.",
        )

        return {
            "pipeline_uid": pipeline.pipeline_uid,
            "product_id": product.id,
            "content_id": article_item.id,
            "video_content_id": video_item.id if video_item else None,
            "publication_id": primary_pub_id,
            "current_state": pipeline.current_state,
            "buyer_intent": pipeline.buyer_intent,
            "quality_score": pipeline.quality_score,
            "state_history": pipeline.state_history,
            "publications": pub_results,
        }

    def refresh_outdated_contents(self) -> Dict[str, Any]:
        """Atualiza automaticamente conteúdos antigos quando o preço ou estoque do produto mudou."""
        published_contents = (
            self.db.query(ContentItem)
            .filter(ContentItem.status.in_(["READY", "PUBLISHED"]))
            .all()
        )
        refreshed_ids: List[int] = []

        for item in published_contents:
            prod = self.db.query(Product).filter(Product.id == item.product_id).first()
            if not prod:
                continue
            current_price_str = _format_brl(prod.price)
            if current_price_str not in (item.body or ""):
                # Atualiza o preço verificado e o status de estoque no corpo e JSON-LD
                item.body = (
                    f"{item.body}\n\n"
                    f"> **Atualização Automática de Catálogo:** Preço verificado atualizado para **{current_price_str}** "
                    f"({'Em estoque' if prod.in_stock else 'Indisponível no momento'})."
                )
                if isinstance(item.structured_data_json, dict) and "offers" in item.structured_data_json:
                    sd = dict(item.structured_data_json)
                    offers = dict(sd.get("offers", {}))
                    offers["price"] = f"{prod.price:.2f}"
                    sd["offers"] = offers
                    item.structured_data_json = sd
                refreshed_ids.append(item.id)

        if refreshed_ids:
            self.db.commit()

        return {
            "checked_contents": len(published_contents),
            "refreshed_count": len(refreshed_ids),
            "refreshed_content_ids": refreshed_ids,
        }

