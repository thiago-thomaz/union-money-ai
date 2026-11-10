"""Motor de Aprendizado Comercial e Experimentação A/B (Seção 6).

Regras obrigatórias:
- Analisa: produtos publicados, visualizações, cliques, CTR, conversões confirmadas,
  comissões aprovadas, comissões canceladas, receita líquida, desempenho por categoria,
  canal e formato de conteúdo.
- Utiliza inicialmente estatística descritiva e regras determinísticas.
- Machine learning somente quando existir volume suficiente de dados reais (>= 100 conversões confirmadas).
- Não inventa capacidade de previsão.
- Inclui mecanismo de experimentação A/B para títulos, formatos e chamadas (CTAs).
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.campaign import Experiment, ExperimentVariant
from app.models.click import ClickLog, VisitorAggregate
from app.models.commission import Commission
from app.models.conversion import Conversion
from app.models.financial import Expense, RevenueRecord
from app.models.marketplace import Category
from app.models.product import Product
from app.models.publication import Publication

MIN_CONVERSIONS_FOR_ML = 100


class CommercialLearningEngine:
    """Motor determinístico e estatístico de aprendizado comercial."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_learning_report(self, include_synthetic: bool = False) -> Dict[str, Any]:
        """Consolida métricas reais e aprendizados determinísticos da operação."""
        prod_q = self.db.query(Product).filter(Product.is_active.is_(True))
        if not include_synthetic:
            prod_q = prod_q.filter(Product.is_synthetic_test.is_(False))
        published_products_count = (
            self.db.query(func.count(func.distinct(Publication.product_id)))
            .filter(Publication.status == "PUBLISHED")
            .scalar()
            or 0
        )

        # Visualizações (visitantes agregados + views de publicações)
        agg_views = self.db.query(func.coalesce(func.sum(VisitorAggregate.page_views), 0)).scalar() or 0
        pub_views = self.db.query(func.coalesce(func.sum(Publication.views_count), 0)).scalar() or 0
        total_views = int(agg_views + pub_views)

        # Cliques válidos humanos
        total_clicks = (
            self.db.query(func.count(ClickLog.id))
            .filter(ClickLog.is_valid_human.is_(True))
            .scalar()
            or 0
        )

        ctr_pct = round((total_clicks / total_views) * 100.0, 2) if total_views > 0 else 0.0

        # Conversões confirmadas
        confirmed_conversions = (
            self.db.query(func.count(Conversion.id))
            .filter(Conversion.status == "CONFIRMED")
            .scalar()
            or 0
        )

        # Comissões aprovadas e canceladas
        approved_commissions_brl = float(
            self.db.query(func.coalesce(func.sum(Commission.amount), 0.0))
            .filter(Commission.status.in_(["APPROVED", "PAID"]))
            .scalar()
            or 0.0
        )
        cancelled_commissions_brl = float(
            self.db.query(func.coalesce(func.sum(Commission.amount), 0.0))
            .filter(Commission.status == "CANCELLED")
            .scalar()
            or 0.0
        )

        # Receita líquida (Receitas confirmadas - Despesas pagas)
        confirmed_revenue_brl = float(
            self.db.query(func.coalesce(func.sum(RevenueRecord.amount), 0.0))
            .filter(RevenueRecord.status == "CONFIRMED")
            .scalar()
            or 0.0
        )
        paid_expenses_brl = float(
            self.db.query(func.coalesce(func.sum(Expense.amount), 0.0))
            .filter(Expense.status == "PAID")
            .scalar()
            or 0.0
        )
        net_revenue_brl = round(confirmed_revenue_brl - paid_expenses_brl, 2)

        # Desempenho por canal
        channel_performance = self._analyze_by_channel()

        # Desempenho por formato de conteúdo
        format_performance = self._analyze_by_content_format()

        # Desempenho por categoria
        category_performance = self._analyze_by_category()

        # Verifica elegibilidade honesta para Machine Learning
        ml_ready = confirmed_conversions >= MIN_CONVERSIONS_FOR_ML
        engine_mode = (
            "MACHINE_LEARNING_ELIGIBLE"
            if ml_ready
            else "DETERMINISTIC_STATISTICS_AND_RULES"
        )

        recommendations = self._build_deterministic_recommendations(
            total_views=total_views,
            total_clicks=total_clicks,
            ctr_pct=ctr_pct,
            confirmed_conversions=confirmed_conversions,
            approved_commissions_brl=approved_commissions_brl,
            cancelled_commissions_brl=cancelled_commissions_brl,
            channel_performance=channel_performance,
        )

        return {
            "engine_mode": engine_mode,
            "ml_status_message": (
                "Volume suficiente atingido para modelos estatísticos avançados."
                if ml_ready
                else f"Modo estatístico e determinístico ativo ({confirmed_conversions}/{MIN_CONVERSIONS_FOR_ML} conversões reais para habilitar ML)."
            ),
            "metrics": {
                "published_products": published_products_count,
                "total_views": total_views,
                "total_clicks": total_clicks,
                "ctr_pct": ctr_pct,
                "confirmed_conversions": confirmed_conversions,
                "conversion_rate_pct": round((confirmed_conversions / total_clicks) * 100.0, 2) if total_clicks > 0 else 0.0,
                "approved_commissions_brl": round(approved_commissions_brl, 2),
                "cancelled_commissions_brl": round(cancelled_commissions_brl, 2),
                "confirmed_revenue_brl": round(confirmed_revenue_brl, 2),
                "paid_expenses_brl": round(paid_expenses_brl, 2),
                "net_revenue_brl": net_revenue_brl,
            },
            "by_channel": channel_performance,
            "by_content_format": format_performance,
            "by_category": category_performance,
            "recommendations": recommendations,
        }

    def _analyze_by_channel(self) -> List[Dict[str, Any]]:
        click_rows = (
            self.db.query(ClickLog.channel, func.count(ClickLog.id))
            .filter(ClickLog.is_valid_human.is_(True))
            .group_by(ClickLog.channel)
            .all()
        )
        conv_rows = (
            self.db.query(Conversion.channel, func.count(Conversion.id), func.coalesce(func.sum(Conversion.order_value), 0.0))
            .filter(Conversion.status == "CONFIRMED")
            .group_by(Conversion.channel)
            .all()
        )
        conv_map = {row[0]: (int(row[1]), float(row[2])) for row in conv_rows}
        channels = set([r[0] for r in click_rows] + list(conv_map.keys()))

        results = []
        for ch in sorted(channels):
            clicks = next((int(r[1]) for r in click_rows if r[0] == ch), 0)
            convs, order_vol = conv_map.get(ch, (0, 0.0))
            results.append(
                {
                    "channel": ch,
                    "clicks": clicks,
                    "confirmed_conversions": convs,
                    "conversion_rate_pct": round((convs / clicks) * 100.0, 2) if clicks > 0 else 0.0,
                    "gross_order_volume_brl": round(order_vol, 2),
                }
            )
        return results

    def _analyze_by_content_format(self) -> List[Dict[str, Any]]:
        conv_rows = (
            self.db.query(Conversion.content_format, func.count(Conversion.id), func.coalesce(func.sum(Conversion.order_value), 0.0))
            .filter(Conversion.status == "CONFIRMED")
            .group_by(Conversion.content_format)
            .all()
        )
        return [
            {
                "content_format": row[0],
                "confirmed_conversions": int(row[1]),
                "gross_order_volume_brl": round(float(row[2]), 2),
            }
            for row in conv_rows
        ]

    def _analyze_by_category(self) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(
                Category.name,
                func.count(Conversion.id),
                func.coalesce(func.sum(Conversion.order_value), 0.0),
            )
            .join(Product, Product.category_id == Category.id)
            .join(Conversion, Conversion.product_id == Product.id)
            .filter(Conversion.status == "CONFIRMED")
            .group_by(Category.name)
            .all()
        )
        return [
            {
                "category": row[0],
                "confirmed_conversions": int(row[1]),
                "gross_order_volume_brl": round(float(row[2]), 2),
            }
            for row in rows
        ]

    @staticmethod
    def _build_deterministic_recommendations(
        total_views: int,
        total_clicks: int,
        ctr_pct: float,
        confirmed_conversions: int,
        approved_commissions_brl: float,
        cancelled_commissions_brl: float,
        channel_performance: List[Dict[str, Any]],
    ) -> List[str]:
        recs: List[str] = []
        if total_views == 0 and total_clicks == 0:
            recs.append("AGUARDANDO DADOS REAIS: Publique conteúdos de produtos com score >= 75 para iniciar a coleta de tráfego e cliques.")
            return recs

        if total_views >= 50 and ctr_pct < 1.5:
            recs.append("CTR abaixo de 1.5%: inicie um experimento A/B de títulos e chamadas para ação (CTA) nos produtos com maior número de visualizações.")

        if total_clicks >= 30 and confirmed_conversions == 0:
            recs.append("Cliques registrados sem conversões confirmadas: revise a adequação entre a promessa do conteúdo e o preço/estoque atual na página de destino.")

        total_comm = approved_commissions_brl + cancelled_commissions_brl
        if total_comm > 0 and (cancelled_commissions_brl / total_comm) > 0.25:
            recs.append("Taxa de cancelamento de comissões superior a 25%: priorize vendedores de melhor reputação e pagamentos instantâneos (Pix/Cartão).")

        if channel_performance:
            best_ch = max(channel_performance, key=lambda c: (c["confirmed_conversions"], c["clicks"]))
            if best_ch["clicks"] > 0:
                recs.append(f"Canal com melhor tração atual: {best_ch['channel']} ({best_ch['clicks']} cliques, {best_ch['confirmed_conversions']} conversões).")

        return recs


def evaluate_ab_experiment(db: Session, experiment_id: int) -> Dict[str, Any]:
    """Avalia estatisticamente um experimento A/B (teste Z de duas proporções) sem inventar resultados."""
    exp = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not exp:
        raise ValueError(f"Experimento {experiment_id} não encontrado.")

    variants = (
        db.query(ExperimentVariant)
        .filter(ExperimentVariant.experiment_id == exp.id)
        .order_by(ExperimentVariant.variant_key.asc())
        .all()
    )
    if len(variants) < 2:
        return {
            "experiment_id": exp.id,
            "status": exp.status,
            "conclusion": "INSUFFICIENT_VARIANTS",
            "message": "São necessárias pelo menos 2 variantes para comparação A/B.",
        }

    variant_metrics = []
    for v in variants:
        ctr = (v.clicks / v.impressions) if v.impressions > 0 else 0.0
        cr = (v.conversions / v.clicks) if v.clicks > 0 else 0.0
        variant_metrics.append(
            {
                "id": v.id,
                "variant_key": v.variant_key,
                "headline_or_cta": v.headline_or_cta,
                "content_format": v.content_format,
                "impressions": v.impressions,
                "clicks": v.clicks,
                "conversions": v.conversions,
                "ctr_pct": round(ctr * 100.0, 2),
                "conversion_rate_pct": round(cr * 100.0, 2),
            }
        )

    # Verifica amostra mínima (mínimo de 30 impressões por variante para análise de CTR)
    if any(v.impressions < 30 for v in variants):
        return {
            "experiment_id": exp.id,
            "status": exp.status,
            "conclusion": "COLLECTING_SAMPLES",
            "confidence_level": 0.0,
            "winning_variant_id": None,
            "message": "Aguardando amostra mínima de 30 impressões por variante.",
            "variants": variant_metrics,
        }

    # Ordena pelas melhores taxas de clique (ou conversão se houver conversões)
    total_convs = sum(v.conversions for v in variants)
    if total_convs >= 10:
        ranked = sorted(variants, key=lambda v: (v.conversions / max(1, v.clicks)), reverse=True)
        p1 = ranked[0].conversions / max(1, ranked[0].clicks)
        p2 = ranked[1].conversions / max(1, ranked[1].clicks)
        n1 = max(1, ranked[0].clicks)
        n2 = max(1, ranked[1].clicks)
    else:
        ranked = sorted(variants, key=lambda v: (v.clicks / max(1, v.impressions)), reverse=True)
        p1 = ranked[0].clicks / max(1, ranked[0].impressions)
        p2 = ranked[1].clicks / max(1, ranked[1].impressions)
        n1 = max(1, ranked[0].impressions)
        n2 = max(1, ranked[1].impressions)

    p_pool = ((p1 * n1) + (p2 * n2)) / (n1 + n2)
    se = math.sqrt(max(1e-9, p_pool * (1.0 - p_pool) * ((1.0 / n1) + (1.0 / n2))))
    z_score = abs(p1 - p2) / se if se > 0 else 0.0

    # Converte Z-score em nível de confiança aproximado via função erro (erf)
    confidence = round(math.erf(z_score / math.sqrt(2.0)) * 100.0, 2)
    exp.confidence_level = confidence

    winner_id: Optional[int] = None
    conclusion = "INCONCLUSIVE"
    if confidence >= 90.0 and p1 > p2:
        winner_id = ranked[0].id
        exp.winning_variant_id = winner_id
        exp.status = "COMPLETED"
        exp.completed_at = datetime.now(timezone.utc)
        conclusion = "WINNER_CONFIRMED"

    db.commit()

    return {
        "experiment_id": exp.id,
        "status": exp.status,
        "conclusion": conclusion,
        "confidence_level": confidence,
        "winning_variant_id": winner_id,
        "variants": variant_metrics,
    }

