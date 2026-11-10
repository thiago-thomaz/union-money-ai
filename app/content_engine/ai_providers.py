"""Arquitetura de Provedores de IA Gratuita e Inspeção de Hardware (Seção 3).

Provedores:
1. NativePythonProvider (Padrão garantido, 100% nativo, baseado em templates, regras e dados reais).
2. LocalLLMProvider (Opcional para modelos leves locais apenas após verificação de RAM/CPU; sem exigir GPU).
3. OptionalExternalProvider (Opcional; nunca bloqueia a operação quando indisponível).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
import httpx
import psutil
from app.config import settings
from app.core.logging import logger


class HardwareInspector:
    """Avalia CPU e memória RAM antes de permitir uso de modelos locais leves."""

    MIN_RAM_GB_FOR_LOCAL_LLM = 4.0
    MIN_AVAILABLE_RAM_GB = 1.2

    @classmethod
    def inspect(cls) -> Dict[str, Any]:
        vm = psutil.virtual_memory()
        total_gb = round(vm.total / (1024**3), 2)
        available_gb = round(vm.available / (1024**3), 2)
        cpu_cores = psutil.cpu_count(logical=True) or 1
        cpu_usage_pct = psutil.cpu_percent(interval=0.05)

        eligible_for_light_local_llm = (
            total_gb >= cls.MIN_RAM_GB_FOR_LOCAL_LLM
            and available_gb >= cls.MIN_AVAILABLE_RAM_GB
            and cpu_usage_pct < 90.0
        )
        return {
            "cpu_cores": cpu_cores,
            "cpu_usage_pct": cpu_usage_pct,
            "total_ram_gb": total_gb,
            "available_ram_gb": available_gb,
            "gpu_required": False,
            "eligible_for_light_local_llm": eligible_for_light_local_llm,
        }


class BaseAIProvider(ABC):
    """Interface base para provedores de geração de texto comercial factual."""

    provider_name: str = "BaseAIProvider"

    @abstractmethod
    def is_available(self) -> bool:
        """Retorna True se o provedor estiver pronto e saudável."""

    @abstractmethod
    def enhance_editorial_section(self, base_text: str, context: Dict[str, Any]) -> str:
        """Produz ou refina uma seção textual mantendo estrita fidelidade aos dados reais."""


class NativePythonProvider(BaseAIProvider):
    """Provedor nativo Python baseado em regras, estrutura editorial e dados verificados."""

    provider_name = "NativePythonProvider"

    def is_available(self) -> bool:
        return True

    def enhance_editorial_section(self, base_text: str, context: Dict[str, Any]) -> str:
        return base_text.strip()


class LocalLLMProvider(BaseAIProvider):
    """Provedor opcional para modelo leve local (ex.: Ollama/llama.cpp HTTP local) sem exigir GPU."""

    provider_name = "LocalLLMProvider"

    def __init__(self, endpoint_url: str | None = None, model_name: str | None = None) -> None:
        self.endpoint_url = (endpoint_url or settings.LOCAL_LLM_URL).strip()
        self.model_name = (model_name or settings.LOCAL_LLM_MODEL).strip()
        self._fallback = NativePythonProvider()

    def is_available(self) -> bool:
        if not self.endpoint_url:
            return False
        hw = HardwareInspector.inspect()
        if not hw["eligible_for_light_local_llm"]:
            return False
        try:
            with httpx.Client(timeout=1.5) as client:
                resp = client.get(self.endpoint_url)
                return resp.status_code < 500
        except Exception:
            return False

    def enhance_editorial_section(self, base_text: str, context: Dict[str, Any]) -> str:
        if not self.is_available():
            return self._fallback.enhance_editorial_section(base_text, context)
        try:
            prompt = (
                "Reescreva de forma clara e objetiva sem inventar especificações, preços ou testes pessoais:\n\n"
                f"{base_text}"
            )
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.endpoint_url.rstrip('/')}/api/generate",
                    json={"model": self.model_name, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                out = resp.json().get("response", "").strip()
                return out if out else base_text
        except Exception as exc:
            logger.warning("LocalLLMProvider indisponível (%s); usando NativePythonProvider.", exc)
            return self._fallback.enhance_editorial_section(base_text, context)


class OptionalExternalProvider(BaseAIProvider):
    """Provedor externo gratuito opcional; jamais bloqueia a operação quando offline."""

    provider_name = "OptionalExternalProvider"

    def __init__(self, endpoint_url: str | None = None) -> None:
        self.endpoint_url = (endpoint_url or settings.OPTIONAL_EXTERNAL_AI_URL).strip()
        self._fallback = NativePythonProvider()

    def is_available(self) -> bool:
        if not self.endpoint_url:
            return False
        try:
            with httpx.Client(timeout=1.5) as client:
                resp = client.get(self.endpoint_url)
                return resp.status_code < 500
        except Exception:
            return False

    def enhance_editorial_section(self, base_text: str, context: Dict[str, Any]) -> str:
        if not self.is_available():
            return self._fallback.enhance_editorial_section(base_text, context)
        return self._fallback.enhance_editorial_section(base_text, context)


class AIProviderRouter:
    """Seleciona o provedor disponível priorizando estabilidade local sem bloquear a operação."""

    def __init__(self) -> None:
        self.native = NativePythonProvider()
        self.local_llm = LocalLLMProvider()
        self.external = OptionalExternalProvider()

    def get_active_provider(self) -> BaseAIProvider:
        if self.local_llm.is_available():
            return self.local_llm
        if self.external.is_available():
            return self.external
        return self.native

    def status_report(self) -> Dict[str, Any]:
        hw = HardwareInspector.inspect()
        active = self.get_active_provider()
        return {
            "active_provider": active.provider_name,
            "hardware": hw,
            "providers": {
                "NativePythonProvider": {"available": True, "requires_gpu": False, "paid": False},
                "LocalLLMProvider": {
                    "available": self.local_llm.is_available(),
                    "configured_url": bool(self.local_llm.endpoint_url),
                    "requires_gpu": False,
                    "paid": False,
                },
                "OptionalExternalProvider": {
                    "available": self.external.is_available(),
                    "configured_url": bool(self.external.endpoint_url),
                    "paid": False,
                },
            },
        }


ai_provider_router = AIProviderRouter()

