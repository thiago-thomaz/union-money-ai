"""UNION CONTENT ENGINE (Seção 2 e Seção 3).

Produz os 13 formatos oficiais com:
- Provedor de IA gratuito/nativo (NativePythonProvider / LocalLLMProvider / OptionalExternalProvider).
- Verificação rigorosa de dados (nunca finge ter testado fisicamente o produto; sinaliza informações
  não verificadas para confirmação na loja).
- Avisos obrigatórios de afiliado (incluindo declaração específica da Amazon quando aplicável).
- Cálculo automático do Content Quality Score (0 a 100) e bloqueio de publicação automática se abaixo do mínimo.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session
from app.config import settings
from app.content_engine.ai_providers import ai_provider_router
from app.content_engine.quality import (
    AMAZON_ASSOCIATE_DISCLOSURE,
    STANDARD_AFFILIATE_DISCLOSURE,
    ContentQualityScorer,
)
from app.content_engine.seo import UnionSEOEngine, generate_seo_metadata, slugify
from app.content_engine.thumbnails import generate_product_thumbnail
from app.content_engine.video import UnionVideoEngine
from app.models.content import ContentItem
from app.models.marketplace import Category, Marketplace
from app.models.product import Product


def _format_brl(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "Preço pendente de confirmação na loja oficial"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _build_legal_footer(marketplace_slug: str, marketplace_name: str) -> str:
    lines = [
        "---",
        f"**Aviso de Transparência Comercial:** {STANDARD_AFFILIATE_DISCLOSURE}",
    ]
    if marketplace_slug.lower() == "amazon":
        lines.append(f"**Declaração Associados Amazon:** {AMAZON_ASSOCIATE_DISCLOSURE}")
    lines.append(
        f"*Nota Editorial: Não realizamos testes físicos de bancada neste item; as informações refletem "
        f"os dados públicos verificados na oferta do {marketplace_name} e estão sujeitas a alteração de preço "
        f"e estoque pelo vendedor sem aviso prévio.*"
    )
    return "\n\n".join(lines)


def generate_illustrative_infographic(
    product: Product,
    category_name: str,
    marketplace_name: str,
) -> Path:
    """Cria imagem ilustrativa original (1080x1080) usando textos e formas no Pillow sem usar imagens de terceiros."""
    width, height = 1080, 1080
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(30, 30), (width - 30, height - 30)], outline=(16, 185, 129), width=6)
    draw.rectangle([(65, 65), (width - 65, 165)], fill=(16, 185, 129))
    draw.text((90, 102), f"FICHA INFORMATIVA • {category_name.upper()}", fill=(11, 17, 32))

    draw.text((80, 220), product.title[:58], fill=(248, 250, 252))
    draw.text((80, 275), f"Plataforma: {marketplace_name}", fill=(148, 163, 184))

    # Blocos visuais de indicadores verificados
    boxes = [
        ("PREÇO CONSULTADO", _format_brl(product.price)),
        ("DISPONIBILIDADE", "Em estoque" if product.in_stock else "Confirmar estoque na loja"),
        (
            "NOTA PÚBLICA",
            f"{product.rating:.1f}/5.0 ({product.review_count or 0} avaliações)"
            if product.rating is not None
            else "A confirmar na página do vendedor",
        ),
        (
            "SCORE DE OPORTUNIDADE",
            f"{product.opportunity_score:.1f}/100 ({product.score_classification})"
            if product.opportunity_score is not None
            else "Aguardando dados complementares",
        ),
    ]
    y = 360
    for label, val in boxes:
        draw.rectangle([(80, y), (width - 80, y + 125)], fill=(30, 41, 59), outline=(51, 65, 85), width=3)
        draw.text((110, y + 28), label, fill=(148, 163, 184))
        draw.text((110, y + 68), str(val), fill=(52, 211, 153))
        y += 145

    draw.text((80, height - 90), "PUBLICIDADE • LINK DE AFILIADO | UNION OFERTAS", fill=(148, 163, 184))

    fname = f"ilustrativo-{product.id}-{slugify(product.title)[:40]}.png"
    out_path = settings.storage_dir / "thumbnails" / fname
    img.save(out_path, format="PNG")
    return out_path


class UnionContentEngine:
    """Motor unificado de produção de conteúdo comercial (13 formatos + Content Quality Score)."""

    SUPPORTED_FORMATS = (
        "ARTICLE",
        "BUYING_GUIDE",
        "COMPARISON",
        "PRODUCT_LIST",
        "EDITORIAL_REVIEW",
        "VIDEO_SCRIPT",
        "SHORT_VIDEO",
        "SOCIAL_CAPTION",
        "SEO_TITLE",
        "PRODUCT_DESCRIPTION",
        "CALL_TO_ACTION",
        "ILLUSTRATIVE_IMAGE",
        "THUMBNAIL",
    )

    def __init__(self, db: Session) -> None:
        self.db = db
        self.quality_scorer = ContentQualityScorer()

    def produce(
        self,
        product: Product,
        content_type: str = "ARTICLE",
        campaign_id: Optional[int] = None,
        comparison_product: Optional[Product] = None,
        aspect_ratio: str = "9:16",
    ) -> ContentItem:
        """Gera, valida qualidade e persiste um item de conteúdo para o produto informado."""
        fmt = content_type.upper().strip()
        mp = self.db.query(Marketplace).filter(Marketplace.id == product.marketplace_id).first()
        cat = self.db.query(Category).filter(Category.id == product.category_id).first()
        mp_name = mp.name if mp else "Marketplace"
        mp_slug = mp.slug if mp else "mercadolivre"
        cat_name = cat.name if cat else "Geral"
        aff_link = product.affiliate_url or product.product_url

        seo_meta = generate_seo_metadata(product.title, cat_name, mp_name)
        footer = _build_legal_footer(mp_slug, mp_name)
        price_str = _format_brl(product.price)

        verif_map = product.data_verification_map or {}
        rating_line = (
            f"Nota pública registrada: {product.rating:.1f}/5.0 com {product.review_count or 0} avaliações."
            if product.rating is not None
            else "Avaliações dos compradores: Informação pendente de confirmação diretamente na página oficial do vendedor."
        )
        spec_line = (
            product.description.strip()
            if product.description and product.description.strip()
            else "Especificações técnicas detalhadas: precisam de confirmação direta na ficha oficial do fabricante/vendedor antes da compra."
        )

        provider = ai_provider_router.get_active_provider()
        media_path: Optional[str] = None
        subtitle_path: Optional[str] = None
        used_ratio: Optional[str] = None

        if fmt == "BUYING_GUIDE":
            title = f"Guia de Compra: Como Escolher em {cat_name} — Análise de {product.title}"
            body = (
                f"# {title}\n\n"
                f"## 1. O que observar antes de comprar em {cat_name}\n"
                f"Ao pesquisar opções de **{cat_name}**, compare a finalidade de uso, a reputação do vendedor no {mp_name} "
                f"e a relação entre o valor cobrado ({price_str}) e a utilidade prática.\n\n"
                f"## 2. Ficha Verificada: {product.title}\n"
                f"- **Preço consultado:** {price_str}\n"
                f"- **Disponibilidade:** {'Em estoque no momento da consulta' if product.in_stock else 'Indisponível / Confirmar na loja'}\n"
                f"- **Resumo técnico:** {spec_line}\n"
                f"- **Reputação:** {rating_line}\n\n"
                f"## 3. Como consultar a oferta oficial\n"
                f"👉 [Consultar oferta atualizada no {mp_name}]({aff_link})\n\n"
                f"{footer}"
            )
            cta = f"Consultar guia e oferta no {mp_name}"

        elif fmt == "COMPARISON":
            other = comparison_product
            if other is None:
                other = (
                    self.db.query(Product)
                    .filter(
                        Product.category_id == product.category_id,
                        Product.id != product.id,
                        Product.is_active.is_(True),
                        Product.is_synthetic_test.is_(False),
                    )
                    .first()
                )
            other_title = other.title if other else f"Alternativa Padrão da Categoria {cat_name}"
            other_price = _format_brl(other.price) if other else "Consulte na categoria"
            title = f"Comparativo: {product.title} vs {other_title}"
            body = (
                f"# {title}\n\n"
                f"## Comparação Objetiva de Ficha e Preço ({cat_name})\n\n"
                f"### Opção 1: {product.title}\n"
                f"- **Preço verificado:** {price_str}\n"
                f"- **Plataforma:** {mp_name}\n"
                f"- **Detalhes:** {spec_line}\n"
                f"- **Link Oficial:** [Conferir {product.title}]({aff_link})\n\n"
                f"### Opção 2: {other_title}\n"
                f"- **Preço de referência:** {other_price}\n"
                f"- **Indicação:** Compare as especificações e frete para sua região antes de decidir.\n\n"
                f"## Conclusão Editorial\n"
                f"Escolha com base na sua necessidade real de uso e orçamento disponível.\n\n"
                f"{footer}"
            )
            cta = f"Comparar preço atual no {mp_name}"

        elif fmt == "PRODUCT_LIST":
            related: List[Product] = (
                self.db.query(Product)
                .filter(
                    Product.category_id == product.category_id,
                    Product.is_active.is_(True),
                    Product.is_synthetic_test.is_(False),
                )
                .order_by(Product.opportunity_score.desc().nullslast())
                .limit(5)
                .all()
            )
            if product not in related:
                related.insert(0, product)
            title = f"Melhores Opções em {cat_name}: Seleção Verificada ({mp_name})"
            list_lines = []
            for idx, item in enumerate(related, start=1):
                item_link = item.affiliate_url or item.product_url
                list_lines.append(
                    f"### {idx}. {item.title}\n"
                    f"- **Preço verificado:** {_format_brl(item.price)}\n"
                    f"- **Disponibilidade:** {'Em estoque' if item.in_stock else 'Verificar na loja'}\n"
                    f"- **Link de Afiliado:** [Consultar no marketplace]({item_link})"
                )
            body = (
                f"# {title}\n\n"
                f"Selecionamos produtos monitorados na categoria **{cat_name}** com base em dados públicos verificados:\n\n"
                + "\n\n".join(list_lines)
                + f"\n\n{footer}"
            )
            cta = f"Conferir lista completa no {mp_name}"

        elif fmt == "EDITORIAL_REVIEW":
            title = f"Avaliação Editorial: {product.title} ({mp_name})"
            body = (
                f"# {title}\n\n"
                f"## 1. Proposta do Produto\n"
                f"O **{product.title}** integra o catálogo de *{cat_name}* no {mp_name}. {spec_line}\n\n"
                f"## 2. Análise de Preço e Condições Verificadas\n"
                f"- **Valor consultado:** {price_str}\n"
                f"- **Status de estoque:** {'Disponível' if product.in_stock else 'Indisponível no momento'}\n"
                f"- **Avaliações públicas:** {rating_line}\n"
                f"- **Status dos dados:** Campos verificados: {', '.join(sorted(k for k, v in verif_map.items() if v == 'VERIFIED')) or 'preço e disponibilidade'}.\n\n"
                f"## 3. Acesso à Oferta Oficial\n"
                f"👉 [Conferir oferta verificada no {mp_name}]({aff_link})\n\n"
                f"{footer}"
            )
            cta = f"Consultar oferta verificada no {mp_name}"

        elif fmt == "VIDEO_SCRIPT":
            title = f"Roteiro de Vídeo 7 Etapas: {product.title[:75]}"
            scenes = UnionVideoEngine.build_7_step_scenes(
                product_title=product.title,
                price=product.price,
                marketplace_name=mp_name,
                category_name=cat_name,
                verified_features=spec_line,
            )
            scene_blocks = [
                f"### Etapa {s['step']} — {s['label']} ({s['duration_sec']}s)\n"
                f"- **Locução/Texto:** {s['headline']}\n"
                f"- **Complemento:** {s['subtext']}"
                for s in scenes
            ]
            body = (
                f"# {title}\n\n"
                + "\n\n".join(scene_blocks)
                + f"\n\n**Link Oficial de Afiliado:** {aff_link}\n\n{footer}"
            )
            cta = f"Conferir no {mp_name}"

        elif fmt == "SHORT_VIDEO":
            vid_res = UnionVideoEngine.generate_video(
                product_title=product.title,
                price=product.price,
                marketplace_name=mp_name,
                aspect_ratio=aspect_ratio,
                category_name=cat_name,
                verified_features=spec_line,
            )
            title = f"Vídeo Curto ({vid_res['aspect_ratio']}): {product.title[:70]}"
            media_path = vid_res.get("video_path") or vid_res.get("thumbnail_path")
            subtitle_path = vid_res.get("subtitle_path")
            used_ratio = vid_res.get("aspect_ratio")
            body = (
                f"# {title}\n\n"
                f"## Resumo do Vídeo Gerado ({vid_res['status']})\n"
                f"- **Produto:** {product.title}\n"
                f"- **Preço consultado:** {price_str}\n"
                f"- **Formato:** {vid_res['aspect_ratio']}\n"
                f"- **Arquivo de mídia:** `{media_path}`\n"
                f"- **Legendas sincronizadas (.srt):** `{subtitle_path}`\n"
                f"- **Link Oficial:** {aff_link}\n\n"
                f"{footer}"
            )
            cta = f"Assistir e conferir oferta no {mp_name}"

        elif fmt == "SOCIAL_CAPTION":
            title = f"Legenda Social Verificada: {product.title[:70]}"
            amz_line = f"\n{AMAZON_ASSOCIATE_DISCLOSURE}" if mp_slug.lower() == "amazon" else ""
            body = (
                f"# Oferta Verificada em {cat_name}: {product.title}\n\n"
                f"• Preço consultado no {mp_name}: {price_str}\n"
                f"• {rating_line}\n"
                f"• Link oficial de afiliado: {aff_link}\n\n"
                f"{STANDARD_AFFILIATE_DISCLOSURE}{amz_line}\n"
                f"Preços e estoque sujeitos a alteração pelo vendedor.\n"
                f"#publicidade #afiliado #{slugify(cat_name).replace('-', '')}"
            )
            cta = "Acesse o link de afiliado oficial"

        elif fmt == "SEO_TITLE":
            title = seo_meta["seo_title"]
            body = (
                f"# Títulos Otimizados para Busca Comercial: {product.title}\n\n"
                f"1. **{seo_meta['seo_title']}**\n"
                f"2. **{product.title} por {price_str}: Ficha e Onde Comprar ({mp_name})**\n"
                f"3. **Guia {cat_name}: {product.title} atende bem no dia a dia?**\n\n"
                f"Link verificado: {aff_link}\n\n"
                f"{footer}"
            )
            cta = f"Ver oferta no {mp_name}"

        elif fmt == "PRODUCT_DESCRIPTION":
            title = f"Descrição Factual: {product.title}"
            body = (
                f"# {title}\n\n"
                f"## Dados Verificados na Plataforma ({mp_name})\n"
                f"{spec_line}\n\n"
                f"- **Categoria:** {cat_name}\n"
                f"- **Preço consultado:** {price_str}\n"
                f"- **Disponibilidade:** {'Em estoque' if product.in_stock else 'Confirmar na loja'}\n"
                f"- **Link de Afiliado:** {aff_link}\n\n"
                f"{footer}"
            )
            cta = f"Consultar ficha completa no {mp_name}"

        elif fmt == "CALL_TO_ACTION":
            title = f"Chamadas para Ação (CTAs Éticos): {product.title[:70]}"
            body = (
                f"# Chamadas para Ação Verificadas — {product.title}\n\n"
                f"- **CTA Principal:** Consultar preço atual ({price_str}) e estoque no {mp_name}\n"
                f"- **CTA Comparativo:** Conferir especificações oficiais de {product.title} na loja\n"
                f"- **URL Rastreável:** {aff_link}\n\n"
                f"{footer}"
            )
            cta = f"Consultar preço atual no {mp_name}"

        elif fmt == "ILLUSTRATIVE_IMAGE":
            img_path = generate_illustrative_infographic(product, cat_name, mp_name)
            media_path = str(img_path)
            title = f"Infográfico Ilustrativo Original: {product.title[:70]}"
            body = (
                f"# {title}\n\n"
                f"Composição gráfica original gerada localmente com dados verificados de **{product.title}** ({price_str}).\n\n"
                f"- **Arquivo gerado:** `{media_path}`\n"
                f"- **Link de Afiliado:** {aff_link}\n\n"
                f"{footer}"
            )
            cta = f"Ver oferta oficial no {mp_name}"

        elif fmt == "THUMBNAIL":
            thumb_path = generate_product_thumbnail(product.title, product.price, mp_name)
            media_path = str(thumb_path)
            title = f"Miniatura Oficial (1280x720): {product.title[:70]}"
            body = (
                f"# {title}\n\n"
                f"Miniatura PNG 1280x720 gerada com preço consultado ({price_str}) para **{product.title}**.\n\n"
                f"- **Arquivo:** `{media_path}`\n"
                f"- **Link de Afiliado:** {aff_link}\n\n"
                f"{footer}"
            )
            cta = f"Conferir no {mp_name}"

        else:
            # ARTICLE (Padrão)
            title = seo_meta["seo_title"]
            body = (
                f"# {title}\n\n"
                f"## 1. Visão Geral e Contexto na Categoria {cat_name}\n"
                f"O **{product.title}** é uma alternativa comercializada no **{mp_name}** voltada para consumidores que "
                f"buscam soluções práticas em *{cat_name}*. {spec_line}\n\n"
                f"## 2. Condições Comerciais Verificadas\n"
                f"- **Preço verificado no momento da análise:** {price_str}\n"
                f"- **Disponibilidade:** {'Em estoque' if product.in_stock else 'Indisponível / Confirmar na loja'}\n"
                f"- **Avaliações públicas:** {rating_line}\n\n"
                f"## 3. Como Conferir a Oferta com Segurança\n"
                f"👉 **[Consultar oferta oficial de {product.title} no {mp_name}]({aff_link})**\n\n"
                f"{footer}"
            )
            cta = f"Ver oferta oficial no {mp_name}"

        enhanced_body = provider.enhance_editorial_section(
            body,
            {"product_title": product.title, "price": product.price, "marketplace": mp_name},
        )

        quality_eval = self.quality_scorer.evaluate(
            title=title,
            body=enhanced_body,
            product_title=product.title,
            verified_price=product.price,
            marketplace_slug=mp_slug,
            seo_keywords=seo_meta["keywords"],
        )

        json_ld = UnionSEOEngine.build_structured_data_jsonld(
            product_title=product.title,
            description=product.description or seo_meta["meta_description"],
            price=product.price,
            currency=product.currency,
            in_stock=bool(product.in_stock),
            product_url=aff_link,
            marketplace_name=mp_name,
            category_name=cat_name,
            rating=product.rating,
            review_count=product.review_count,
        )

        item_status = "READY" if quality_eval["eligible_for_auto_publish"] else "BLOCKED_LOW_QUALITY"

        content_item = ContentItem(
            product_id=product.id,
            campaign_id=campaign_id,
            content_type=fmt,
            title=title,
            slug=f"{slugify(title)[:75]}-{product.id}-{fmt.lower()[:8]}",
            body=enhanced_body,
            call_to_action=cta,
            seo_keywords=seo_meta["keywords"],
            meta_description=seo_meta["meta_description"],
            media_path=media_path,
            subtitle_path=subtitle_path,
            aspect_ratio=used_ratio,
            ai_provider_used=provider.provider_name,
            quality_score=quality_eval["quality_score"],
            quality_breakdown=quality_eval,
            structured_data_json=json_ld,
            status=item_status,
        )
        self.db.add(content_item)
        self.db.commit()
        self.db.refresh(content_item)
        return content_item

