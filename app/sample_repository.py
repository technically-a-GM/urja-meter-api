"""Deterministic, entirely fictional data for local development and tests.

These are NOT readings retrieved from Urja Meter Ops.
"""

from datetime import datetime

from app.models import ConsumptionReading, ConsumptionResponse, LocationResponse, Meter, MeterListResponse
from app.repository import MeterNotFound

_METERS = [
    Meter(meter_id="DEMO-001", name="Example North", status="active", attributes={"source": "fictional demo"}),
    Meter(meter_id="DEMO-002", name="Example South", status="active", attributes={"source": "fictional demo"}),
    Meter(meter_id="DEMO-003", name="Example East", status="inactive", attributes={"source": "fictional demo"}),
]

_READINGS = {
    "DEMO-001": [("2026-01-01T00:00:00Z", 24.5), ("2026-01-02T00:00:00Z", 27.1)],
    "DEMO-002": [("2026-01-01T00:00:00Z", 18.8), ("2026-01-02T00:00:00Z", 21.3)],
    "DEMO-003": [],
}


class SampleMeterRepository:
    async def list_meters(
        self, limit: int, offset: int, search: str | None = None,
        status: str | None = None, dt_code: str | None = None,
    ) -> MeterListResponse:
        meters = _METERS
        if search:
            meters = [m for m in meters if search.casefold() in m.meter_id.casefold()]
        if status:
            meters = [m for m in meters if (m.status or "").casefold() == status.casefold()]
        if dt_code:
            meters = []
        return MeterListResponse(items=meters[offset : offset + limit], total=len(meters), limit=limit, offset=offset)

    async def get_meter(self, meter_id: str) -> Meter:
        for meter in _METERS:
            if meter.meter_id == meter_id:
                return meter
        raise MeterNotFound(meter_id)

    async def get_location(self, meter_id: str) -> LocationResponse:
        meter = await self.get_meter(meter_id)
        return LocationResponse(meter_id=meter_id, latitude=meter.latitude, longitude=meter.longitude)

    async def get_consumption(
        self,
        meter_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ConsumptionResponse:
        await self.get_meter(meter_id)
        readings = [ConsumptionReading(timestamp=datetime.fromisoformat(ts.replace("Z", "+00:00")), kwh=kwh)
                    for ts, kwh in _READINGS[meter_id]]
        if start is not None:
            readings = [reading for reading in readings if reading.timestamp >= start]
        if end is not None:
            readings = [reading for reading in readings if reading.timestamp <= end]
        return ConsumptionResponse(meter_id=meter_id, readings=readings)
