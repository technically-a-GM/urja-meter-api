"""Domain interface; outward API is independent of the portal's protocol."""

from datetime import datetime
from typing import Protocol

from app.models import ConsumptionResponse, LocationResponse, Meter, MeterListResponse


class MeterNotFound(Exception):
    pass


class PortalIntegrationPending(Exception):
    pass


class UpstreamUnavailable(Exception):
    pass


class PortalAuthenticationRequired(Exception):
    pass


class MeterRepository(Protocol):
    async def list_meters(
        self, limit: int, offset: int, search: str | None = None,
        status: str | None = None, dt_code: str | None = None,
    ) -> MeterListResponse: ...

    async def get_meter(self, meter_id: str) -> Meter: ...

    async def get_location(self, meter_id: str) -> LocationResponse: ...

    async def get_consumption(
        self, meter_id: str, start: datetime | None = None, end: datetime | None = None
    ) -> ConsumptionResponse: ...
