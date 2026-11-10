"""Interface base para conectores de redes sociais (sem spam e sem automação proibida)."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseSocialConnector(ABC):
    """Classe base para publicação ou exportação assistida em redes sociais."""

    channel_slug: str = "social"
    channel_name: str = "Rede Social"

    @abstractmethod
    def check_status(self) -> Dict[str, Any]:
        """Verifica se credenciais oficiais de API estão configuradas."""

    @abstractmethod
    def publish_or_export(self, title: str, body: str, media_path: str | None = None) -> Dict[str, Any]:
        """Publica via API oficial quando configurada ou gera pacote de exportação manual."""

