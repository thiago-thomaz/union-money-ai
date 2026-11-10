"""Gerador de Landing Pages estáticas/responsivas para produtos de afiliados."""

from pathlib import Path
from app.config import settings
from app.content_engine.seo import slugify
from app.models.product import Product


def build_product_landing_page(product: Product, marketplace_name: str, tracked_url: str) -> Path:
    """Gera página HTML5 responsiva com aviso claro de afiliado e salva em storage/publications."""
    price_str = f"R$ {product.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{product.title} - Análise e Oferta ({marketplace_name})</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        .card {{ max-width: 720px; margin: 0 auto; background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 2rem; }}
        .badge {{ display: inline-block; background: #10b981; color: #052e16; font-weight: 700; padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.85rem; }}
        .price {{ font-size: 2rem; color: #34d399; font-weight: 800; margin: 1rem 0; }}
        .cta {{ display: inline-block; background: #10b981; color: #022c22; text-decoration: none; font-weight: 700; padding: 0.9rem 1.8rem; border-radius: 8px; margin-top: 1rem; }}
        .disclaimer {{ margin-top: 2rem; font-size: 0.8rem; color: #94a3b8; border-top: 1px solid #334155; padding-top: 1rem; }}
    </style>
</head>
<body>
    <main class="card">
        <span class="badge">OFERTA VERIFICADA • {marketplace_name.upper()}</span>
        <h1>{product.title}</h1>
        <p>{product.description or 'Produto selecionado pela relação entre utilidade e avaliação no marketplace.'}</p>
        <div class="price">{price_str}</div>
        <a class="cta" href="{tracked_url}" rel="nofollow sponsored" target="_blank">Conferir no {marketplace_name}</a>
        <div class="disclaimer">
            Transparência: Esta página contém links de afiliados oficiais ({marketplace_name}). Preço e disponibilidade estão sujeitos a alteração pela loja.
        </div>
    </main>
</body>
</html>"""
    fname = f"lp-{product.id}-{slugify(product.title)[:40]}.html"
    out_path = settings.storage_dir / "publications" / fname
    out_path.write_text(html, encoding="utf-8")
    return out_path

