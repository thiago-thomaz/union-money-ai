"""Conector YouTube Data API v3 / Exportação de Roteiro e Shorts."""

from typing import Any, Dict
from app.config import settings
from app.integrations.social.base import BaseSocialConnector


class YouTubeConnector(BaseSocialConnector):
    channel_slug = "YOUTUBE"
    channel_name = "YouTube"

    def check_status(self) -> Dict[str, Any]:
        configured = bool(settings.YOUTUBE_API_KEY.strip())
        return {
            "channel": self.channel_name,
            "status": "READY" if configured else "MANUAL_EXPORT_MODE",
            "has_api_credentials": configured,
        }

    def publish_or_export(self, title: str, body: str, media_path: str | None = None) -> Dict[str, Any]:
        if not settings.YOUTUBE_API_KEY.strip():
            return {
                "channel": self.channel_slug,
                "status": "EXPORTED_FOR_MANUAL",
                "message": "YOUTUBE_API_KEY não configurada. Pacote de vídeo/descrição pronto para upload manual.",
                "title": title,
                "media_path": media_path,
            }
        return {
            "channel": self.channel_slug,
            "status": "READY_FOR_OAUTH_UPLOAD",
            "message": "Credencial detectada; pronto para envio autenticado respeitando limites de cota do YouTube.",
            "title": title,
        }

