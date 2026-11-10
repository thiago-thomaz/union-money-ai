"""Avaliador de Qualidade Editorial e Factual (Content Quality Score 0 a 100 - Seção 3).

Critérios avaliados:
1. Originalidade (15 pts)
2. Clareza (15 pts)
3. Relevância (15 pts)
4. Precisão factual (15 pts) - Bloqueia se afirmar teste pessoal falso ou inventar preço.
5. Ortografia / Estrutura (10 pts)
6. SEO (10 pts)
7. Transparência comercial (10 pts)
8. Identificação de publicidade / afiliado (10 pts)
"""

from typing import Any, Dict, List
from app.config import settings

FORBIDDEN_FALSE_CLAIMS = (
    "testamos em nosso laboratório",
    "testei pessoalmente por",
    "usei durante meses",
    "compramos e desmontamos",
    "garantia de enriquecimento",
    "últimas unidades corra",
    "oferta acaba em 5 minutos",
)

STANDARD_AFFILIATE_DISCLOSURE = (
    "Esta página contém links de afiliados. Podemos receber uma comissão por compras qualificadas, sem custo adicional para você."
)
AMAZON_ASSOCIATE_DISCLOSURE = "Como associado da Amazon, eu ganho com compras qualificadas."


class ContentQualityScorer:
    """Calcula o Content Quality Score (0 a 100) e impede publicação automática abaixo da nota mínima."""

    def __init__(self, min_score: float | None = None) -> None:
        self.min_score = min_score if min_score is not None else settings.MIN_CONTENT_QUALITY_SCORE

    def evaluate(
        self,
        title: str,
        body: str,
        product_title: str,
        verified_price: float,
        marketplace_slug: str = "mercadolivre",
        seo_keywords: str | None = None,
    ) -> Dict[str, Any]:
        text_lower = f"{title}\n{body}".lower()
        violations: List[str] = []

        # 1. Verifica afirmações falsas proibidas (teste pessoal inexistente ou falsa escassez)
        for phrase in FORBIDDEN_FALSE_CLAIMS:
            if phrase in text_lower:
                violations.append(f"Afirmação não verificada ou escassez artificial detectada: '{phrase}'")

        # 2. Originalidade (15 pts) - diversidade vocabular e tamanho útil
        words = [w.strip(".,!?:;()[]\"'") for w in body.split() if len(w) > 2]
        unique_ratio = (len(set(w.lower() for w in words)) / len(words)) if words else 0.0
        originality_pts = round(min(15.0, (min(1.0, len(words) / 80.0) * 9.0) + (min(1.0, unique_ratio / 0.45) * 6.0)), 2)

        # 3. Clareza (15 pts) - parágrafos e listas estruturadas
        paragraphs = [p for p in body.split("\n\n") if p.strip()]
        clarity_pts = 15.0 if len(paragraphs) >= 2 and len(title.strip()) >= 10 else 9.0

        # 4. Relevância (15 pts) - menção ao produto real
        prod_tokens = [t.lower() for t in product_title.split() if len(t) > 3]
        matched_tokens = sum(1 for t in prod_tokens if t in text_lower)
        rel_ratio = (matched_tokens / len(prod_tokens)) if prod_tokens else 1.0
        relevance_pts = round(15.0 * min(1.0, max(0.3, rel_ratio)), 2)

        # 5. Precisão factual (15 pts)
        price_dot = f"{verified_price:.2f}"
        price_comma = f"{verified_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        has_accurate_price = (price_dot in body) or (price_comma in body)
        if violations:
            factual_pts = 0.0
        elif has_accurate_price:
            factual_pts = 15.0
        else:
            factual_pts = 10.5

        # 6. Ortografia e limpeza estrutural (10 pts)
        has_broken_placeholders = ("{{" in body) or ("}}" in body) or ("undefined" in text_lower)
        orthography_pts = 2.0 if has_broken_placeholders else 10.0
        if has_broken_placeholders:
            violations.append("Marcadores de template não preenchidos detectados.")

        # 7. SEO (10 pts)
        has_headings = ("#" in body) or ("<h" in text_lower) or ("[" in body)
        has_keywords = bool(seo_keywords and len(seo_keywords.strip()) >= 5)
        seo_pts = (6.0 if has_headings else 3.0) + (4.0 if has_keywords else 2.0)

        # 8. Transparência comercial (10 pts)
        has_price_variation_notice = any(
            term in text_lower
            for term in ("alteração", "alteracao", "atualizado", "sem custo adicional", "sujeito")
        )
        transparency_pts = 10.0 if has_price_variation_notice else 4.0

        # 9. Identificação de publicidade e afiliado (10 pts)
        has_aff_disclosure = any(
            term in text_lower for term in ("afiliado", "comissão", "comissao", "#afiliado", "publicidade")
        )
        if marketplace_slug.lower() == "amazon":
            has_amazon_req = "como associado da amazon" in text_lower
            ad_disclosure_pts = 10.0 if (has_aff_disclosure and has_amazon_req) else (5.0 if has_aff_disclosure else 0.0)
            if not has_amazon_req:
                violations.append("Ausência da declaração obrigatória do Associados Amazon.")
        else:
            ad_disclosure_pts = 10.0 if has_aff_disclosure else 0.0
            if not has_aff_disclosure:
                violations.append("Ausência de identificação explícita de link de afiliado/publicidade.")

        total_score = round(
            originality_pts
            + clarity_pts
            + relevance_pts
            + factual_pts
            + orthography_pts
            + seo_pts
            + transparency_pts
            + ad_disclosure_pts,
            2,
        )

        # Se houver violação factual ou de transparência obrigatória, bloqueia aprovação automática
        eligible = (total_score >= self.min_score) and (len(violations) == 0)

        return {
            "quality_score": total_score,
            "min_required_score": self.min_score,
            "eligible_for_auto_publish": eligible,
            "violations": violations,
            "breakdown": {
                "originality": originality_pts,
                "clarity": clarity_pts,
                "relevance": relevance_pts,
                "factual_precision": factual_pts,
                "orthography": orthography_pts,
                "seo": seo_pts,
                "commercial_transparency": transparency_pts,
                "ad_disclosure": ad_disclosure_pts,
            },
        }

