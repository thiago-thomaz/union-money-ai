"""Exceções customizadas do sistema UNION MONEY AI."""


class UnionMoneyError(Exception):
    """Exceção base de domínio do UNION MONEY AI."""

    def __init__(self, message: str, code: str = "UNION_MONEY_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class InsufficientScoringDataError(UnionMoneyError):
    """Levantada quando não existem dados suficientes para pontuar um produto."""

    def __init__(self, message: str = "Dados insuficientes para atribuir pontuação confiável."):
        super().__init__(message, code="INSUFFICIENT_SCORING_DATA")


class IntegrationError(UnionMoneyError):
    """Erro geral em conectores de marketplaces ou redes sociais."""

    def __init__(self, marketplace: str, message: str, code: str = "INTEGRATION_ERROR"):
        super().__init__(f"[{marketplace}] {message}", code=code)
        self.marketplace = marketplace


class CredentialsMissingError(IntegrationError):
    """Erro levantado quando credenciais oficiais de API não estão configuradas."""

    def __init__(self, marketplace: str, details: str = "Credenciais oficiais não configuradas."):
        super().__init__(marketplace, details, code="CREDENTIALS_MISSING")


class RateLimitExceededError(IntegrationError):
    """Erro levantado quando o limite de requisições do conector é atingido."""

    def __init__(self, marketplace: str, retry_after_seconds: float):
        super().__init__(
            marketplace,
            f"Limite de requisições atingido. Aguarde {retry_after_seconds:.1f}s.",
            code="RATE_LIMIT_EXCEEDED",
        )
        self.retry_after_seconds = retry_after_seconds


class PolicyViolationError(UnionMoneyError):
    """Levantada ao detectar tentativa de spam, clique artificial ou violação de política."""

    def __init__(self, message: str):
        super().__init__(message, code="POLICY_VIOLATION")

