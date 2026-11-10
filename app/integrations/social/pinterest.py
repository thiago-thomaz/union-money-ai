"""Conector Pinterest API v5 / Exportação Assistida de Pins."""

from typing import Any, Dict
from app.config import settings
from app.integrations.social.base import BaseSocialConnector


class PinterestConnector(BaseSocialConnector):
    channel_slug = "PINTEREST"
    channel_name = "Pinterest"

    def check_status(self) -> Dict[str, Any]:
        configured = bool(settings.PINTEREST_ACCESS_TOKEN.strip())
        return {
            "channel": self.channel_name,
            "status": "READY" if configured else "MANUAL_EXPORT_MODE",
            "has_api_credentials": configured,
        }

    def publish_or_export(self, title: str, body: str, media_path: str | None = None) -> Dict[str, Any]:
        if not settings.PINTEREST_ACCESS_TOKEN.strip():
            return {
                "channel": self.channel_slug,
                "status": "EXPORTED_FOR_MANUAL",
                "message": "PINTEREST_ACCESS_TOKEN não configurado. Pin visual e descrição prontos para postagem.",
                "title": title,
                "media_path": media_path,
            }
        return {
            "channel": self.channel_slug,
            "status": "READY_FOR_PINTEREST_API",
            "message": "Token Pinterest API v5 configurado.",
            "title": title,
        }

