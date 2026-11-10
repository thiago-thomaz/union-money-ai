"""Copywriting ético e estruturado (AIDA / PAS) com transparência de link de afiliado."""

from typing import Dict
from app.models.product import Product


def generate_product_copy(product: Product, marketplace_name: str, affiliate_link: str) -> Dict[str, str]:
    """Produz textos comerciais baseados exclusivamente nos dados verificados/estimados do produto."""
    price_str = f"R$ {product.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    discount_note = ""
    if product.original_price and product.original_price > product.price:
        orig_str = f"R$ {product.original_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        discount_pct = round(((product.original_price - product.price) / product.original_price) * 100)
        discount_note = f" (de {orig_str} por {price_str}, economia de {discount_pct}%)"

    rating_note = (
        f"Avaliação média registrada: {product.rating:.1f}/5.0 ({product.review_count or 0} avaliações)."
        if product.rating
        else "Verifique as avaliações mais recentes diretamente na página do vendedor."
    )

    headline = f"Análise e Oferta Verificada: {product.title}"
    body = (
        f"Se você busca custo-benefício em {product.title}, conferimos as condições atuais no {marketplace_name}.\n\n"
        f"• Preço verificado no momento da análise: {price_str}{discount_note}\n"
        f"• Disponibilidade: {'Em estoque' if product.in_stock else 'Estoque limitado / indisponível'}\n"
        f"• {rating_note}\n\n"
        f"Acesse a oferta oficial pelo link abaixo:\n{affiliate_link}\n\n"
        f"Aviso de transparência: Este conteúdo contém link de afiliado oficial ({marketplace_name}). "
        f"O preço e o estoque podem sofrer alterações pela loja sem aviso prévio."
    )
    cta = f"Conferir preço e disponibilidade no {marketplace_name}"
    return {
        "headline": headline,
        "body": body,
        "cta": cta,
    }

