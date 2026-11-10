"""Boletim de Ofertas Opt-In (estritamente anti-spam, apenas para inscritos voluntários)."""

from typing import Dict, List
from app.models.product import Product


def build_optin_digest(products: List[Product]) -> Dict[str, str]:
    """Gera boletim em texto/HTML apenas com oportunidades verificadas e link de descadastro obrigatório."""
    if not products:
        return {
            "subject": "Sem novas oportunidades prioritárias hoje",
            "body": "Nenhuma oportunidade atingiu o score mínimo de envio hoje.",
        }

    lines = ["Resumo de Oportunidades Verificadas (UNION MONEY AI):", ""]
    for p in products:
        lines.append(f"- {p.title}: R$ {p.price:.2f} (Score: {p.opportunity_score or 'N/A'}) -> {p.affiliate_url or p.product_url}")
    lines.append("")
    lines.append("Aviso: Contém links de afiliados. Você recebeu este resumo por inscrição opt-in. Para cancelar, clique em descadastrar.")
    return {
        "subject": f"Top {len(products)} Oportunidades Analisadas",
        "body": "\n".join(lines),
    }

