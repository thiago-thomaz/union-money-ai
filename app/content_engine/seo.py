"""Motor de SEO (UNION SEO ENGINE - Seção 5).

Inclui:
- Pesquisa e classificação de palavras-chave com intenção comercial.
- Agrupamento de temas (Topic Clusters).
- Estrutura H1/H2/H3, títulos SEO, meta descriptions, slugs amigáveis.
- Dados estruturados JSON-LD (Product, Article, BreadcrumbList).
- Sitemap XML e Robots.txt dinâmicos.
- Recomendação de links internos e calendário editorial baseado em demanda e qualidade.
"""

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List
import unicodedata


def slugify(text: str) -> str:
    """Converte um título em slug amigável para URL."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", normalized).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)[:120]


def generate_seo_metadata(product_title: str, category_name: str, marketplace_name: str) -> Dict[str, str]:
    """Gera metadados SEO determinísticos e estruturados para páginas e artigos."""
    clean_title = product_title.strip()
    keywords: List[str] = [
        clean_title.lower(),
        f"{clean_title.lower()} vale a pena",
        f"{clean_title.lower()} {marketplace_name.lower()}",
        f"melhor {category_name.lower()} custo-beneficio",
        f"onde comprar {clean_title.lower()}",
    ]
    return {
        "slug": slugify(clean_title),
        "seo_title": f"{clean_title}: Vale a Pena? Análise de Preço e Ficha ({marketplace_name})",
        "meta_description": (
            f"Análise objetiva sobre {clean_title} na categoria {category_name}. "
            f"Confira preço atualizado, pontos principais e link verificado no {marketplace_name}."
        )[:160],
        "keywords": ", ".join(keywords),
    }


class UnionSEOEngine:
    """Motor completo de otimização para mecanismos de busca focado em intenção comercial."""

    COMMERCIAL_INTENT_TEMPLATES = {
        "BEST_VALUE": "Melhor {category} custo-benefício em {year}",
        "WHICH_TO_BUY": "Qual {product} comprar para o dia a dia?",
        "COMPARISON": "Comparativo: {product} vs alternativas de {category}",
        "BUYING_GUIDE": "Guia de compra: como escolher {category} sem errar",
    }

    @classmethod
    def research_commercial_keywords(cls, product_title: str, category_name: str) -> List[Dict[str, str]]:
        """Gera lista de palavras-chave com classificação explícita de intenção de compra."""
        p_clean = product_title.strip()
        c_clean = category_name.strip()
        return [
            {
                "keyword": f"melhor {p_clean.lower()} custo-benefício",
                "intent": "COMMERCIAL_INVESTIGATION",
                "recommended_format": "BUYING_GUIDE",
            },
            {
                "keyword": f"{p_clean.lower()} vale a pena comprar",
                "intent": "COMMERCIAL_INVESTIGATION",
                "recommended_format": "EDITORIAL_REVIEW",
            },
            {
                "keyword": f"qual {c_clean.lower()} comprar para trabalhar",
                "intent": "PROBLEM_SOLVING",
                "recommended_format": "ARTICLE",
            },
            {
                "keyword": f"comparativo {p_clean.lower()}",
                "intent": "COMPARISON",
                "recommended_format": "COMPARISON",
            },
            {
                "keyword": f"oferta oficial {p_clean.lower()}",
                "intent": "TRANSACTIONAL",
                "recommended_format": "PRODUCT_DESCRIPTION",
            },
        ]

    @classmethod
    def build_topic_clusters(cls, categories_and_products: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Agrupa pautas por cluster temático evitando páginas repetitivas (canibalização)."""
        clusters: Dict[str, List[Dict[str, Any]]] = {}
        seen_slugs = set()
        for item in categories_and_products:
            cat = item.get("category_name", "Geral")
            title = item.get("title", "")
            slug = slugify(title)
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            clusters.setdefault(cat, []).append(
                {
                    "product_id": item.get("id"),
                    "title": title,
                    "slug": slug,
                    "primary_keyword": f"melhor {title.lower()} custo-benefício",
                }
            )
        return clusters

    @classmethod
    def build_structured_data_jsonld(
        cls,
        product_title: str,
        description: str,
        price: float,
        currency: str,
        in_stock: bool,
        product_url: str,
        marketplace_name: str,
        category_name: str,
        rating: float | None = None,
        review_count: int | None = None,
    ) -> Dict[str, Any]:
        """Gera Schema.org JSON-LD (Product + Offer) estritamente fiel aos dados verificados."""
        schema: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": product_title,
            "description": description or f"Análise editorial de {product_title} ({category_name}).",
            "category": category_name,
            "offers": {
                "@type": "Offer",
                "priceCurrency": currency,
                "price": f"{price:.2f}",
                "availability": "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock",
                "url": product_url,
                "seller": {
                    "@type": "Organization",
                    "name": marketplace_name,
                },
            },
        }
        if rating is not None and review_count is not None and review_count > 0:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": f"{rating:.1f}",
                "reviewCount": str(review_count),
            }
        return schema

    @classmethod
    def generate_internal_links(
        cls,
        current_product_id: int,
        related_products: List[Dict[str, Any]],
        category_slug: str,
    ) -> List[Dict[str, str]]:
        """Gera sugestões de links internos relevantes para navegação do leitor e SEO."""
        links = [
            {
                "anchor": "Ver todos os produtos recomendados",
                "url": "/ofertas/recomendados",
            },
            {
                "anchor": f"Mais ofertas na categoria {category_slug}",
                "url": f"/ofertas/categorias/{category_slug}",
            },
        ]
        for prod in related_products[:4]:
            if prod.get("id") != current_product_id:
                links.append(
                    {
                        "anchor": f"Análise: {prod.get('title')}",
                        "url": f"/ofertas/produto/{prod.get('id')}",
                    }
                )
        return links

    @classmethod
    def generate_editorial_calendar(
        cls,
        ranked_products: List[Dict[str, Any]],
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Cria calendário editorial diário priorizando produtos com maior Opportunity Score."""
        formats_cycle = ["EDITORIAL_REVIEW", "BUYING_GUIDE", "COMPARISON", "PRODUCT_LIST", "SHORT_VIDEO"]
        calendar: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for idx, prod in enumerate(ranked_products[:days]):
            pub_date = (now + timedelta(days=idx)).strftime("%Y-%m-%d")
            fmt = formats_cycle[idx % len(formats_cycle)]
            calendar.append(
                {
                    "scheduled_date": pub_date,
                    "product_id": prod["id"],
                    "product_title": prod["title"],
                    "opportunity_score": prod.get("opportunity_score"),
                    "recommended_format": fmt,
                    "target_keyword": f"melhor {prod['title'].lower()} custo-benefício",
                    "intent": "COMMERCIAL_INVESTIGATION",
                }
            )
        return calendar

    @classmethod
    def build_sitemap_xml(cls, base_url: str, urls: List[str]) -> str:
        """Gera XML oficial do Sitemap."""
        clean_base = base_url.rstrip("/")
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entries = []
        for path in urls:
            loc = f"{clean_base}{path if path.startswith('/') else '/' + path}"
            entries.append(
                f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{now_iso}</lastmod>\n    <changefreq>daily</changefreq>\n  </url>"
            )
        body = "\n".join(entries)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n"
            "</urlset>"
        )

    @classmethod
    def build_robots_txt(cls, base_url: str) -> str:
        """Gera arquivo robots.txt permitindo indexação das páginas editoriais."""
        clean_base = base_url.rstrip("/")
        return (
            "User-agent: *\n"
            "Allow: /ofertas\n"
            "Disallow: /api/\n"
            "Disallow: /settings\n"
            f"Sitemap: {clean_base}/sitemap.xml\n"
        )
