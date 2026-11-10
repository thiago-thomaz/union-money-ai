"""Gerador de Roteiros para Vídeos Curtos (Shorts/Reels) e Reviews."""

from typing import Dict
from app.models.product import Product


def generate_video_script(product: Product, marketplace_name: str, affiliate_link: str) -> Dict[str, str]:
    """Cria roteiro estruturado de 45 segundos com gancho, apresentação, benefícios e CTA."""
    price_str = f"R$ {product.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    script_text = (
        f"[00-05s | GANCHO VISUAL]\n"
        f"Procurando {product.title} com bom custo-benefício no {marketplace_name}?\n\n"
        f"[05-20s | PONTOS PRINCIPAIS]\n"
        f"Este modelo se destaca pela relação entre utilidade e faixa de preço ({price_str}). "
        f"{product.description or 'Ideal para quem busca praticidade no dia a dia.'}\n\n"
        f"[20-35s | REPUTAÇÃO E CONFIANÇA]\n"
        f"{f'Possui nota {product.rating:.1f} de 5 estrelas.' if product.rating else 'Vendedor verificado na plataforma.'}\n\n"
        f"[35-45s | CHAMADA PARA AÇÃO + TRANSPARÊNCIA]\n"
        f"O link oficial de afiliado está na descrição/bio para você conferir o preço atualizado: {affiliate_link}"
    )
    return {
        "title": f"Roteiro Short: {product.title[:80]}",
        "body": script_text,
        "cta": f"Confira no link oficial ({marketplace_name})",
    }

