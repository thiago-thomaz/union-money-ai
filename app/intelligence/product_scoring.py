"""Motor de Pontuação de Oportunidade de Produtos (Product Opportunity Score 0 a 100).

Regras estritas:
- Pesos configuráveis (padrão total = 100):
    * Potencial de procura (demand_potential): 20 pontos
    * Qualidade da oferta (offer_quality): 15 pontos
    * Comissão estimada (estimated_commission): 20 pontos
    * Concorrência (competition): 10 pontos
    * Qualidade das avaliações (review_quality): 10 pontos
    * Potencial de conteúdo (content_potential): 10 pontos
    * Confiabilidade das informações (data_reliability): 10 pontos
    * Disponibilidade (availability): 5 pontos
- Não atribui nota quando não existirem dados suficientes.
- Separa explicitamente: VERIFIED (verificados), ESTIMATED (estimados), UNAVAILABLE (indisponíveis).
- Distingue comissão percentual anunciada de comissão efetivamente recebida.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from app.config import settings


class DataStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"


class ScoreClassification(str, Enum):
    PRIORITY = "oportunidade prioritária"       # 90 a 100
    INTERESTING = "oportunidade interessante"  # 75 a 89
    TEST = "testar"                            # 60 a 74
    LOW_PRIORITY = "baixa prioridade"          # 40 a 59
    DISCARD = "descartar"                      # 0 a 39
    INSUFFICIENT = "dados insuficientes"       # Sem nota


@dataclass
class ProductScoringInput:
    """Estrutura de entrada para cálculo do Product Opportunity Score."""

    price: Optional[float] = None
    original_price: Optional[float] = None
    in_stock: Optional[bool] = None
    announced_commission_rate: Optional[float] = None
    effective_commission_rate: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    demand_index: Optional[float] = None          # 0 a 100
    competition_index: Optional[float] = None     # 0 a 100 (quanto menor a concorrência, melhor, ou índice de vantagem competitiva)
    content_potential_index: Optional[float] = None  # 0 a 100
    utility_score: Optional[float] = None         # 0 a 100
    verification_map: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScoringResult:
    """Resultado detalhado e auditável do Product Opportunity Score."""

    score: Optional[float]
    classification: str
    confidence_score: float
    sufficient_data: bool
    reason: Optional[str]
    commission_basis: str
    effective_vs_announced_gap_pct: Optional[float]
    data_separation: Dict[str, list[str]]
    dimension_scores: Dict[str, Dict[str, Any]]
    weights_used: Dict[str, float]


class ProductOpportunityScorer:
    """Motor de cálculo do Product Opportunity Score (0 a 100)."""

    REQUIRED_WEIGHT_KEYS = (
        "demand_potential",
        "offer_quality",
        "estimated_commission",
        "competition",
        "review_quality",
        "content_potential",
        "data_reliability",
        "availability",
    )

    def __init__(self, custom_weights: Optional[Dict[str, float]] = None) -> None:
        base_weights = dict(settings.DEFAULT_SCORING_WEIGHTS)
        if custom_weights:
            for k in self.REQUIRED_WEIGHT_KEYS:
                if k in custom_weights and custom_weights[k] >= 0:
                    base_weights[k] = float(custom_weights[k])

        total_weight = sum(base_weights.values())
        if total_weight <= 0:
            raise ValueError("A soma dos pesos de pontuação deve ser maior que zero.")

        # Normaliza para escala de 100 pontos caso os pesos customizados não somem exatamente 100
        self.weights: Dict[str, float] = {
            k: round((v / total_weight) * 100.0, 4) for k, v in base_weights.items()
        }

    @staticmethod
    def classify_score(score: Optional[float]) -> str:
        """Retorna a classificação oficial de acordo com a faixa de 0 a 100."""
        if score is None:
            return ScoreClassification.INSUFFICIENT.value
        if score >= 90.0:
            return ScoreClassification.PRIORITY.value
        if score >= 75.0:
            return ScoreClassification.INTERESTING.value
        if score >= 60.0:
            return ScoreClassification.TEST.value
        if score >= 40.0:
            return ScoreClassification.LOW_PRIORITY.value
        return ScoreClassification.DISCARD.value

    def evaluate(self, data: ProductScoringInput) -> ScoringResult:
        """Avalia um produto, separando dados verificados, estimados e indisponíveis."""
        verified_fields: list[str] = []
        estimated_fields: list[str] = []
        unavailable_fields: list[str] = []

        def _get_status(field_name: str, value: Any, default_when_present: DataStatus = DataStatus.ESTIMATED) -> DataStatus:
            if value is None:
                unavailable_fields.append(field_name)
                return DataStatus.UNAVAILABLE
            explicit = data.verification_map.get(field_name, "").upper()
            if explicit == DataStatus.VERIFIED.value:
                verified_fields.append(field_name)
                return DataStatus.VERIFIED
            if explicit == DataStatus.ESTIMATED.value:
                estimated_fields.append(field_name)
                return DataStatus.ESTIMATED
            if default_when_present == DataStatus.VERIFIED:
                verified_fields.append(field_name)
                return DataStatus.VERIFIED
            estimated_fields.append(field_name)
            return DataStatus.ESTIMATED

        # 1. Verifica campos essenciais e status de verificação
        price_status = _get_status("price", data.price if (data.price and data.price > 0) else None, DataStatus.VERIFIED)
        stock_status = _get_status("in_stock", data.in_stock, DataStatus.VERIFIED)
        demand_status = _get_status("demand_index", data.demand_index, DataStatus.ESTIMATED)
        comp_status = _get_status("competition_index", data.competition_index, DataStatus.ESTIMATED)
        content_status = _get_status("content_potential_index", data.content_potential_index, DataStatus.ESTIMATED)
        rating_status = _get_status("rating", data.rating, DataStatus.VERIFIED)

        # Separação entre comissão anunciada vs efetivamente recebida
        commission_rate_used: Optional[float] = None
        commission_basis = "UNAVAILABLE"
        gap_pct: Optional[float] = None

        if data.effective_commission_rate is not None and data.effective_commission_rate >= 0:
            commission_rate_used = data.effective_commission_rate
            commission_basis = "EFFECTIVE_REALIZED"
            comm_status = _get_status("effective_commission_rate", data.effective_commission_rate, DataStatus.VERIFIED)
            if data.announced_commission_rate is not None:
                gap_pct = round(data.effective_commission_rate - data.announced_commission_rate, 2)
        elif data.announced_commission_rate is not None and data.announced_commission_rate >= 0:
            commission_rate_used = data.announced_commission_rate
            commission_basis = "ANNOUNCED_ESTIMATE"
            comm_status = _get_status("announced_commission_rate", data.announced_commission_rate, DataStatus.ESTIMATED)
        else:
            comm_status = _get_status("commission_rate", None)

        # Cálculo do indicador de confiança (0 a 100%)
        total_tracked = len(verified_fields) + len(estimated_fields) + len(unavailable_fields)
        if total_tracked > 0:
            raw_conf = (len(verified_fields) * 1.0 + len(estimated_fields) * 0.5) / total_tracked
            confidence_score = round(raw_conf * 100.0, 2)
        else:
            confidence_score = 0.0

        data_separation = {
            "verified": sorted(set(verified_fields)),
            "estimated": sorted(set(estimated_fields)),
            "unavailable": sorted(set(unavailable_fields)),
        }

        # Validação de suficiência de dados:
        # Não atribuir nota se preço, disponibilidade ou comissão não existirem, ou se menos de 5 campos estiverem disponíveis
        available_count = len(verified_fields) + len(estimated_fields)
        if (
            price_status == DataStatus.UNAVAILABLE
            or stock_status == DataStatus.UNAVAILABLE
            or comm_status == DataStatus.UNAVAILABLE
            or available_count < 5
        ):
            return ScoringResult(
                score=None,
                classification=ScoreClassification.INSUFFICIENT.value,
                confidence_score=confidence_score,
                sufficient_data=False,
                reason=(
                    "Dados insuficientes para atribuir nota: são exigidos no mínimo preço válido, "
                    "disponibilidade, taxa de comissão e indicadores mínimos de mercado/produto."
                ),
                commission_basis=commission_basis,
                effective_vs_announced_gap_pct=gap_pct,
                data_separation=data_separation,
                dimension_scores={},
                weights_used=self.weights,
            )

        # Cálculo normalizado (0.0 a 1.0) para cada um dos 8 critérios:
        # 1. Potencial de procura (20 pts)
        demand_norm = self._clamp((data.demand_index if data.demand_index is not None else 50.0) / 100.0)

        # 2. Qualidade da oferta (15 pts) - avalia desconto real e utilidade/preço
        discount_ratio = 0.0
        if data.original_price and data.price and data.original_price > data.price:
            discount_ratio = min(0.5, (data.original_price - data.price) / data.original_price) / 0.5
        utility_norm = (data.utility_score / 100.0) if data.utility_score is not None else 0.65
        offer_norm = self._clamp((discount_ratio * 0.45) + (utility_norm * 0.55))

        # 3. Comissão estimada (20 pts)
        # Taxa de 15%+ ou valor absoluto >= R$ 35 atinge pontuação máxima
        assert commission_rate_used is not None and data.price is not None
        comm_value_brl = data.price * (commission_rate_used / 100.0)
        rate_score = min(1.0, commission_rate_used / 15.0)
        value_score = min(1.0, comm_value_brl / 40.0)
        # Se for apenas comissão anunciada (não efetiva comprovada), aplica fator conservador de 0.90
        conservatism = 1.0 if commission_basis == "EFFECTIVE_REALIZED" else 0.90
        commission_norm = self._clamp(((rate_score * 0.6) + (value_score * 0.4)) * conservatism)

        # 4. Concorrência (10 pts) - competition_index representa saturação (0 = baixa concorrência, 100 = saturado)
        if data.competition_index is not None:
            competition_norm = self._clamp(1.0 - (data.competition_index / 100.0))
        else:
            competition_norm = 0.5

        # 5. Qualidade das avaliações (10 pts)
        if data.rating is not None and data.rating > 0:
            rating_norm = min(1.0, max(0.0, (data.rating - 1.0) / 4.0))
            volume_factor = 1.0
            if data.review_count is not None:
                if data.review_count < 10:
                    volume_factor = 0.65
                elif data.review_count < 50:
                    volume_factor = 0.85
            review_norm = self._clamp(rating_norm * volume_factor)
        else:
            review_norm = 0.40

        # 6. Potencial de conteúdo (10 pts)
        content_norm = self._clamp(
            (data.content_potential_index / 100.0) if data.content_potential_index is not None else 0.55
        )

        # 7. Confiabilidade das informações (10 pts)
        reliability_norm = self._clamp(confidence_score / 100.0)

        # 8. Disponibilidade (5 pts)
        availability_norm = 1.0 if data.in_stock is True else 0.0

        norms = {
            "demand_potential": (demand_norm, demand_status.value),
            "offer_quality": (offer_norm, price_status.value),
            "estimated_commission": (commission_norm, comm_status.value),
            "competition": (competition_norm, comp_status.value),
            "review_quality": (review_norm, rating_status.value),
            "content_potential": (content_norm, content_status.value),
            "data_reliability": (reliability_norm, DataStatus.VERIFIED.value),
            "availability": (availability_norm, stock_status.value),
        }

        dimension_scores: Dict[str, Dict[str, Any]] = {}
        total_score = 0.0

        for key, (norm_val, status_label) in norms.items():
            max_pts = self.weights[key]
            earned_pts = round(norm_val * max_pts, 2)
            total_score += earned_pts
            dimension_scores[key] = {
                "earned_points": earned_pts,
                "max_points": max_pts,
                "normalized_ratio": round(norm_val, 4),
                "data_status": status_label,
            }

        # Se o produto estiver indisponível (fora de estoque), limita o score máximo a 39 (descartar no momento)
        if not data.in_stock:
            total_score = min(total_score, 39.0)

        final_score = round(min(100.0, max(0.0, total_score)), 2)
        classification = self.classify_score(final_score)

        return ScoringResult(
            score=final_score,
            classification=classification,
            confidence_score=confidence_score,
            sufficient_data=True,
            reason=None,
            commission_basis=commission_basis,
            effective_vs_announced_gap_pct=gap_pct,
            data_separation=data_separation,
            dimension_scores=dimension_scores,
            weights_used=self.weights,
        )

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

