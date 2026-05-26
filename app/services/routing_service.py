from __future__ import annotations

import httpx


class RoutingService:
    def __init__(self, routing_service_url: str | None) -> None:
        self._routing_service_url = routing_service_url

    async def route_user_action(self, payload: dict) -> bool:
        if not self._routing_service_url:
            raise RuntimeError("ROUTING_SERVICE_URL no configurado")

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self._routing_service_url, json=payload)
            response.raise_for_status()
        return True