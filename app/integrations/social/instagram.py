"""Conector Instagram Graph API / Exportação Assistida."""

from typing import Any, Dict
from app.config import settings
from app.integrations.social.base import BaseSocialConnector


class InstagramConnector(BaseSocialConnector):
    channel_slug = "INSTAGRAM"
    channel_name = "Instagram"

    def check_status(self) -> Dict[str, Any]:
        configured = bool(settings.INSTAGRAM_ACCESS_TOKEN.strip())
        return {
            "channel": self.channel_name,
            "status": "READY" if configured else "MANUAL_EXPORT_MODE",
            "has_api_credentials": configured,
        }

    def publish_or_export(self, title: str, body: str, media_path: str | None = None) -> Dict[str, Any]:
        if not settings.INSTAGRAM_ACCESS_TOKEN.strip():
            return {
                "channel": self.channel_slug,
                "status": "EXPORTED_FOR_MANUAL",
                "message": "INSTAGRAM_ACCESS_TOKEN não configurado. Legenda e criativo prontos para publicação manual.",
                "title": title,
                "media_path": media_path,
            }
        return {
            "channel": self.channel_slug,
            "status": "READY_FOR_GRAPH_API",
            "message": "Token Meta Graph API configurado.",
            "title": title,
        }

