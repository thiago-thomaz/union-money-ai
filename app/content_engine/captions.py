"""Gerador de Legendas para Redes Sociais com Conformidade CONAR / Políticas de Afiliados."""

from typing import Dict
from app.models.product import Product


def generate_social_caption(product: Product, marketplace_name: str, affiliate_link: str) -> Dict[str, str]:
    """Cria legenda para redes sociais respeitando políticas anti-spam e transparência (#afiliado)."""
    price_str = f"R$ {product.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    caption = (
        f"Achado verificado no {marketplace_name}: {product.title}\n\n"
        f"Preço consultado: {price_str}\n"
        f"Link oficial: {affiliate_link}\n\n"
        f"*Preços sujeitos a alteração pela loja. Contém link de afiliado.\n"
        f"#afiliado #oferta #{marketplace_name.lower().replace(' ', '')}"
    )
    return {
        "title": f"Legenda Social: {product.title[:70]}",
        "body": caption,
        "cta": "Link oficial na descrição",
    }

