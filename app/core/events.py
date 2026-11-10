"""Barramento de eventos interno em memória para desacoplamento de módulos."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List
from app.core.logging import logger


class EventBus:
    """Barramento de eventos síncrono nativo (sem dependências externas)."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = defaultdict(list)
        self._history: List[Dict[str, Any]] = []

    def subscribe(self, event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Inscreve um manipulador para um tipo de evento."""
        self._subscribers[event_type].append(handler)

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publica um evento e notifica todos os assinantes registrados."""
        event_record = {
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(event_record)
        if len(self._history) > 500:
            self._history = self._history[-500:]

        logger.info("Evento emitido: %s", event_type)
        for handler in self._subscribers.get(event_type, []):
            try:
                handler(event_record)
            except Exception as exc:
                logger.error("Erro ao processar handler do evento %s: %s", event_type, exc)

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retorna os últimos eventos emitidos."""
        return list(reversed(self._history[-limit:]))


event_bus = EventBus()

