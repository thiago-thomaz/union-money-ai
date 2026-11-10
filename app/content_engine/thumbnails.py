"""Gerador nativo de Miniaturas (Thumbnails) com Pillow."""

from pathlib import Path
from PIL import Image, ImageDraw
from app.config import settings
from app.content_engine.seo import slugify


def generate_product_thumbnail(
    product_title: str,
    price: float,
    marketplace_name: str,
    output_filename: str | None = None,
) -> Path:
    """Gera uma miniatura gráfica 1280x720 em PNG usando Pillow e salva em storage/thumbnails."""
    width, height = 1280, 720
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Moldura de destaque esmeralda
    draw.rectangle([(24, 24), (width - 24, height - 24)], outline=(16, 185, 129), width=6)
    draw.rectangle([(60, 60), (420, 130)], fill=(16, 185, 129))
    draw.text((80, 82), f"OFERTA | {marketplace_name.upper()}", fill=(15, 23, 42))

    # Título quebrado em linhas
    words = product_title.split()
    lines = []
    current = ""
    for w in words:
        if len(current) + len(w) + 1 <= 42:
            current = f"{current} {w}".strip()
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)

    y_pos = 200
    for line in lines[:4]:
        draw.text((70, y_pos), line, fill=(248, 250, 252))
        y_pos += 55

    price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    draw.rectangle([(60, 500), (580, 610)], fill=(30, 41, 59), outline=(16, 185, 129), width=3)
    draw.text((90, 540), f"PRECO CONSULTADO: {price_str}", fill=(52, 211, 153))
    draw.text((70, 645), "UNION MONEY AI - Conteudo de Afiliado Verificado", fill=(148, 163, 184))

    fname = output_filename or f"thumb-{slugify(product_title)[:50]}.png"
    out_path = settings.storage_dir / "thumbnails" / fname
    img.save(out_path, format="PNG")
    return out_path

