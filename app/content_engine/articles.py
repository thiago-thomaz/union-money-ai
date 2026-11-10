"""Gerador de Artigos de Review e Comparativos Orientados a Conversão Qualificada."""

from typing import Dict
from app.content_engine.seo import generate_seo_metadata
from app.models.product import Product


def generate_review_article(
    product: Product,
    category_name: str,
    marketplace_name: str,
    affiliate_link: str,
) -> Dict[str, str]:
    """Gera artigo completo em Markdown com ficha técnica, avaliação de oportunidade e aviso legal."""
    seo = generate_seo_metadata(product.title, category_name, marketplace_name)
    price_str = f"R$ {product.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    score_str = f"{product.opportunity_score:.1f}/100" if product.opportunity_score is not None else "Em avaliação"

    article_md = f"""# {seo['seo_title']}

**Categoria:** {category_name} | **Marketplace:** {marketplace_name}  
**Índice de Oportunidade Técnica:** {score_str} ({product.score_classification})

## 1. Visão Geral do Produto
O **{product.title}** é uma opção monitorada na categoria de *{category_name}* no {marketplace_name}.
{product.description or 'Destaca-se pela utilidade prática e disponibilidade de entrega nacional.'}

## 2. Condições Comerciais Verificadas
- **Preço no momento da consulta:** {price_str}
- **Disponibilidade:** {'Em estoque' if product.in_stock else 'Indisponível no momento'}
- **Avaliação dos compradores:** {f'{product.rating:.1f}/5.0 ({product.review_count or 0} avaliações)' if product.rating else 'Não informada'}

## 3. Onde Comprar com Segurança
Para verificar o estoque em tempo real e garantir a proteção de compra da plataforma oficial:

👉 **[Acessar página oficial no {marketplace_name}]({affiliate_link})**

---
*Transparência: Atuamos como afiliados oficiais ({marketplace_name}). Ao comprar através do nosso link, podemos receber uma comissão sem qualquer custo adicional para você.*
"""
    return {
        "title": seo["seo_title"],
        "slug": seo["slug"],
        "body": article_md,
        "seo_keywords": seo["keywords"],
        "cta": f"Ver oferta oficial no {marketplace_name}",
    }

