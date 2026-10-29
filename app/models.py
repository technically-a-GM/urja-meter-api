"""Client-facing schemas, separate from the source portal's field names."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Meter(BaseModel):
    meter_id: str = Field(description="Stable meter identifier")
    name: str | None = None
    status: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class MeterListResponse(BaseModel):
    items: list[Meter]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class LocationResponse(BaseModel):
    meter_id: str
    latitude: float | None = None
    longitude: float | None = None


class ConsumptionReading(BaseModel):
    timestamp: datetime = Field(description="Parsed timestamp; portal timezone assumed/configurable")
    timestamp_original: str | None = Field(default=None, description="Original portal date/time, without timezone")
    kwh: float = Field(description="Cumulative active-energy meter register, kWh (not per-interval usage)")
    kvah: float | None = Field(default=None, description="Cumulative apparent-energy register, kVAh")
    voltage_r: float | None = Field(default=None, description="R-phase voltage, as exposed by portal")


class ConsumptionResponse(BaseModel):
    meter_id: str
    readings: list[ConsumptionReading]
    skipped_records: int = Field(default=0, ge=0, description="Number of upstream rows skipped because timestamp or kWh was invalid")
    measurement_type: str = "cumulative_register"
    unit: str = "kWh"


class HealthResponse(BaseModel):
    status: str
    data_source: str
    integration_ready: bool


class TransformerSummary(BaseModel):
    code: str
    name: str | None = Field(default=None, description="Null if conflicting names in the export")
    name_variants: list[str] = Field(default_factory=list)
    feeder_codes: list[str] = Field(default_factory=list)
    meter_count: int = Field(ge=0)
    capacity_kva: float | None = Field(default=None, description="Unavailable in the meter export")
