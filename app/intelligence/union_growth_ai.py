"""UNION GROWTH AI — Motor de Otimização Comercial Automática (Fase 4 - Seção 9).

Avalia automaticamente dados reais da operação:
- Produtos com mais cliques
- Produtos com mais vendas confirmadas
- Produtos com maior comissão paga
- Categorias com melhor conversão
- Canais com melhor retorno
- Conteúdos que geram tráfego
- Palavras-chave com intenção de compra
- Horários com melhor desempenho
- Taxa de cancelamento
- Receita líquida realizada

Atualiza prioridades de produtos, nichos, canais e formatos automaticamente,
respeitando as travas absolutas de segurança financeira (zero gastos automáticos).
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.click import ClickLog, VisitorAggregate
from app.models.commission import Commission
from app.models.content import ContentItem
from app.models.conversion import Conversion
from app.models.financial import Expense
from app.models.marketplace import Category
from app.models.product import Product
from app.models.publication import Publication


class UnionGrowthAI:
    """Motor de inteligência comercial autônoma para priorização baseada em dados reais."""

    SAFETY_CONSTRAINTS = {
        "auto_increase_financial_investment": False,
        "auto_buy_traffic": False,
        "auto_hire_tools": False,
        "auto_make_payments": False,
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    def evaluate_commercial_performance(self) -> Dict[str, Any]:
        """Executa avaliação abrangente de todos os 10 vetores exigidos pela Seção 9."""
        # 1. Produtos com mais cliques válidos
        clicks_by_product = (
            self.db.query(
                ClickLog.product_id,
                func.count(ClickLog.id).label("clicks_count"),
            )
            .filter(ClickLog.is_valid_human.is_(True))
            .group_by(ClickLog.product_id)
            .order_by(func.count(ClickLog.id).desc())
            .limit(10)
            .all()
        )
        product_map = {
            p.id: p for p in self.db.query(Product).all()
        }
        top_products_by_clicks: List[Dict[str, Any]] = []
        for pid, c_count in clicks_by_product:
            prod = product_map.get(pid)
            if prod:
                top_products_by_clicks.append(
                    {
                        "product_id": pid,
                        "title": prod.title,
                        "clicks": int(c_count),
                        "opportunity_score": round(float(prod.opportunity_score or 0.0), 2),
                    }
                )

        # 2. Produtos com mais vendas confirmadas
        sales_by_product = (
            self.db.query(
                Conversion.product_id,
                func.count(Conversion.id).label("sales_count"),
                func.coalesce(func.sum(Conversion.order_value), 0.0).label("gmv_brl"),
            )
            .filter(Conversion.status == "CONFIRMED")
            .group_by(Conversion.product_id)
            .order_by(func.count(Conversion.id).desc())
            .limit(10)
            .all()
        )
        top_products_by_sales: List[Dict[str, Any]] = []
        for pid, s_count, gmv in sales_by_product:
            prod = product_map.get(pid)
            if prod:
                top_products_by_sales.append(
                    {
                        "product_id": pid,
                        "title": prod.title,
                        "confirmed_sales": int(s_count),
                        "gmv_brl": round(float(gmv or 0.0), 2),
                    }
                )

        # 3. Produtos com maior comissão paga
        paid_by_product = (
            self.db.query(
                Commission.product_id,
                func.coalesce(func.sum(Commission.amount), 0.0).label("paid_commission_brl"),
            )
            .filter(Commission.status == "PAID")
            .group_by(Commission.product_id)
            .order_by(func.sum(Commission.amount).desc())
            .limit(10)
            .all()
        )
        top_products_by_paid_commission: List[Dict[str, Any]] = []
        for pid, paid_amt in paid_by_product:
            prod = product_map.get(pid)
            if prod:
                top_products_by_paid_commission.append(
                    {
                        "product_id": pid,
                        "title": prod.title,
                        "paid_commission_brl": round(float(paid_amt or 0.0), 2),
                    }
                )

        # 4. Categorias com melhor taxa de conversão
        categories = {c.id: c for c in self.db.query(Category).all()}
        cat_clicks: Dict[int, int] = defaultdict(int)
        cat_sales: Dict[int, int] = defaultdict(int)
        for pid, c_count in self.db.query(ClickLog.product_id, func.count(ClickLog.id)).filter(ClickLog.is_valid_human.is_(True)).group_by(ClickLog.product_id).all():
            prod = product_map.get(pid)
            if prod and prod.category_id:
                cat_clicks[prod.category_id] += int(c_count)

        for pid, s_count in self.db.query(Conversion.product_id, func.count(Conversion.id)).filter(Conversion.status == "CONFIRMED").group_by(Conversion.product_id).all():
            prod = product_map.get(pid)
            if prod and prod.category_id:
                cat_sales[prod.category_id] += int(s_count)

        top_categories_by_conversion: List[Dict[str, Any]] = []
        for cid, cat in categories.items():
            clicks_c = cat_clicks.get(cid, 0)
            sales_c = cat_sales.get(cid, 0)
            conv_rate = round((sales_c / clicks_c) * 100.0, 2) if clicks_c > 0 else 0.0
            top_categories_by_conversion.append(
                {
                    "category_id": cid,
                    "category_name": cat.name,
                    "slug": cat.slug,
                    "clicks": clicks_c,
                    "confirmed_sales": sales_c,
                    "conversion_rate_pct": conv_rate,
                }
            )
        top_categories_by_conversion.sort(
            key=lambda x: (x["conversion_rate_pct"], x["confirmed_sales"], x["clicks"]),
            reverse=True,
        )

        # 5. Canais com melhor retorno
        channel_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"clicks": 0, "sales": 0, "paid_commission_brl": 0.0}
        )
        for ch, cnt in self.db.query(ClickLog.channel, func.count(ClickLog.id)).filter(ClickLog.is_valid_human.is_(True)).group_by(ClickLog.channel).all():
            channel_stats[ch or "DIRECT"]["clicks"] += int(cnt)

        for conv in self.db.query(Conversion).filter(Conversion.status == "CONFIRMED").all():
            ch = conv.channel or "DIRECT"
            channel_stats[ch]["sales"] += 1
            paid_comm = (
                self.db.query(func.coalesce(func.sum(Commission.amount), 0.0))
                .filter(Commission.conversion_id == conv.id, Commission.status == "PAID")
                .scalar()
            )
            channel_stats[ch]["paid_commission_brl"] += float(paid_comm or 0.0)

        best_channels: List[Dict[str, Any]] = []
        for ch, st in channel_stats.items():
            best_channels.append(
                {
                    "channel": ch,
                    "clicks": st["clicks"],
                    "confirmed_sales": st["sales"],
                    "paid_commission_brl": round(st["paid_commission_brl"], 2),
                }
            )
        best_channels.sort(
            key=lambda x: (x["paid_commission_brl"], x["confirmed_sales"], x["clicks"]),
            reverse=True,
        )

        # 6. Conteúdos que geram tráfego e melhores formatos
        publications = self.db.query(Publication).order_by(Publication.views_count.desc()).limit(10).all()
        content_map = {c.id: c for c in self.db.query(ContentItem).all()}
        top_contents_by_traffic: List[Dict[str, Any]] = []
        format_performance: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"items": 0, "views": 0, "avg_quality": 0.0}
        )
        for c in content_map.values():
            format_performance[c.content_type]["items"] += 1
            format_performance[c.content_type]["avg_quality"] += float(c.quality_score or 0.0)

        for pub in publications:
            c_item = content_map.get(pub.content_id)
            views = int(pub.views_count or 0)
            if c_item:
                format_performance[c_item.content_type]["views"] += views
                top_contents_by_traffic.append(
                    {
                        "content_id": c_item.id,
                        "title": c_item.title,
                        "content_type": c_item.content_type,
                        "channel": pub.channel,
                        "views": views,
                        "quality_score": round(float(c_item.quality_score or 0.0), 2),
                    }
                )

        # Visitas agregadas por produto/publicação
        visitor_rows = self.db.query(VisitorAggregate).all()
        total_unique_visitors = sum(int(v.unique_visitors or 0) for v in visitor_rows)

        # 7. Palavras-chave com intenção comercial
        commercial_intent_keywords: List[Dict[str, Any]] = []
        seen_kw = set()
        for c_item in sorted(content_map.values(), key=lambda x: x.quality_score, reverse=True):
            if c_item.seo_keywords:
                for kw in [k.strip() for k in c_item.seo_keywords.split(",") if k.strip()]:
                    kw_lower = kw.lower()
                    if kw_lower not in seen_kw:
                        seen_kw.add(kw_lower)
                        commercial_intent_keywords.append(
                            {
                                "keyword": kw,
                                "product_id": c_item.product_id,
                                "intent": "COMMERCIAL_INVESTIGATION",
                            }
                        )
                    if len(commercial_intent_keywords) >= 15:
                        break
            if len(commercial_intent_keywords) >= 15:
                break

        # 8. Horários com melhor desempenho (baseado nos horários reais de cliques e conversões)
        hour_counter: Dict[int, Dict[str, int]] = defaultdict(lambda: {"clicks": 0, "conversions": 0})
        for clk in self.db.query(ClickLog).filter(ClickLog.is_valid_human.is_(True)).all():
            if clk.clicked_at:
                hour_counter[clk.clicked_at.hour]["clicks"] += 1
        for conv in self.db.query(Conversion).filter(Conversion.status == "CONFIRMED").all():
            if conv.occurred_at:
                hour_counter[conv.occurred_at.hour]["conversions"] += 1

        best_performing_hours = [
            {
                "hour_utc": hr,
                "clicks": stats["clicks"],
                "conversions": stats["conversions"],
                "performance_index": stats["conversions"] * 5 + stats["clicks"],
            }
            for hr, stats in hour_counter.items()
        ]
        best_performing_hours.sort(key=lambda x: x["performance_index"], reverse=True)

        # 9. Taxa de cancelamento real
        total_conversions = self.db.query(func.count(Conversion.id)).scalar() or 0
        cancelled_conversions = (
            self.db.query(func.count(Conversion.id))
            .filter(Conversion.status == "CANCELLED")
            .scalar()
            or 0
        )
        cancellation_rate_pct = (
            round((cancelled_conversions / total_conversions) * 100.0, 2)
            if total_conversions > 0
            else 0.0
        )

        # 10. Receita líquida realizada (somente comissões PAID menos despesas reais)
        paid_commissions_total = float(
            self.db.query(func.coalesce(func.sum(Commission.amount), 0.0))
            .filter(Commission.status == "PAID")
            .scalar()
            or 0.0
        )
        total_expenses = float(
            self.db.query(func.coalesce(func.sum(Expense.amount), 0.0)).scalar() or 0.0
        )
        net_realized_revenue_brl = round(paid_commissions_total - total_expenses, 2)

        return {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "top_products_by_clicks": top_products_by_clicks,
            "top_products_by_sales": top_products_by_sales,
            "top_products_by_paid_commission": top_products_by_paid_commission,
            "top_categories_by_conversion": top_categories_by_conversion,
            "best_channels": best_channels,
            "top_contents_by_traffic": top_contents_by_traffic,
            "total_unique_visitors": total_unique_visitors,
            "commercial_intent_keywords": commercial_intent_keywords,
            "best_performing_hours": best_performing_hours[:6],
            "cancellation_rate_pct": cancellation_rate_pct,
            "paid_commissions_total_brl": round(paid_commissions_total, 2),
            "total_expenses_brl": round(total_expenses, 2),
            "net_realized_revenue_brl": net_realized_revenue_brl,
            "safety_constraints": self.SAFETY_CONSTRAINTS,
        }

    def update_priorities_automatically(self) -> Dict[str, Any]:
        """Atualiza pesos de campanhas e prioridades de produtos/nichos sem jamais gastar dinheiro."""
        perf = self.evaluate_commercial_performance()

        top_paid_ids = {p["product_id"] for p in perf["top_products_by_paid_commission"] if p["paid_commission_brl"] > 0}
        top_sales_ids = {p["product_id"] for p in perf["top_products_by_sales"] if p["confirmed_sales"] > 0}
        top_click_ids = {p["product_id"] for p in perf["top_products_by_clicks"] if p["clicks"] > 0}

        updated_campaigns = 0
        for camp in self.db.query(Campaign).filter(Campaign.is_active.is_(True)).all():
            new_weight = 1.0
            if camp.product_id in top_paid_ids:
                new_weight = 2.0
            elif camp.product_id in top_sales_ids:
                new_weight = 1.6
            elif camp.product_id in top_click_ids:
                new_weight = 1.25

            if abs((camp.priority_weight or 1.0) - new_weight) > 0.01:
                camp.priority_weight = new_weight
                updated_campaigns += 1

        self.db.commit()

        best_niche = (
            perf["top_categories_by_conversion"][0]["category_name"]
            if perf["top_categories_by_conversion"]
            else "Tecnologia e Eletrônicos"
        )
        best_channel = (
            perf["best_channels"][0]["channel"]
            if perf["best_channels"]
            else "UNION_OFERTAS"
        )

        return {
            "status": "OPTIMIZED",
            "updated_campaigns_count": updated_campaigns,
            "recommended_focus": {
                "best_niche": best_niche,
                "best_channel": best_channel,
                "prioritized_product_ids": list(top_paid_ids | top_sales_ids | top_click_ids)[:10],
                "recommended_formats": ["ARTICLE", "COMPARISON", "SHORT_VIDEO"],
            },
            "safety_constraints_enforced": self.SAFETY_CONSTRAINTS,
            "performance_snapshot": perf,
        }

