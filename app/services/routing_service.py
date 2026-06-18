from __future__ import annotations

import logging

import httpx


logger = logging.getLogger(__name__)


class RoutingService:
    def __init__(self, routing_service_url: str | None) -> None:
        self._routing_service_url = routing_service_url

    async def route_user_action(self, payload: dict) -> bool:
        if not self._routing_service_url:
            logger.warning("ROUTING_SERVICE_URL no configurado; omitiendo el ruteo de la acción")
            return False

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                response = await client.post(self._routing_service_url, json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Routing service returned %s for %s: %s",
                    exc.response.status_code,
                    self._routing_service_url,
                    exc,
                )
                return False
            except httpx.RequestError as exc:
                logger.warning("Routing service request failed for %s: %s", self._routing_service_url, exc)
                return False

        return True