"""FastAPI routes for meter and transformer data."""

from datetime import datetime
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Path, Query

from app.config import Settings, get_settings
from app.export_snapshot import MeterExportSnapshot
from app.models import ConsumptionResponse, HealthResponse, LocationResponse, Meter, MeterListResponse, TransformerSummary
from app.portal_client import UrjaPortalClient
from app.repository import (
    MeterNotFound, MeterRepository, PortalAuthenticationRequired,
    PortalIntegrationPending, UpstreamUnavailable,
)
from app.sample_repository import SampleMeterRepository

app = FastAPI(
    title="Urja Meter API",
    description=(
        "Read-only API for Urja Meter Ops."
    ),
    version="0.7.0",
)


@lru_cache
def _get_sample_repository() -> SampleMeterRepository:
    return SampleMeterRepository()


def get_repository(settings: Settings = Depends(get_settings)) -> MeterRepository:
    if settings.data_source == "sample":
        return _get_sample_repository()
    # Preserve in-memory session between requests; rebuild if settings object
    # changes (e.g. dependency overrides, configuration reload).
    existing = getattr(app.state, "live_repository", None)
    if existing is None or existing.settings is not settings:
        existing = UrjaPortalClient(settings)
        app.state.live_repository = existing
    return existing


def _raise_api_error(exc: Exception) -> None:
    if isinstance(exc, MeterNotFound):
        raise HTTPException(status_code=404, detail="Meter not found") from exc
    if isinstance(exc, PortalAuthenticationRequired):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, PortalIntegrationPending):
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    if isinstance(exc, UpstreamUnavailable):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise exc


@app.get("/health", response_model=HealthResponse, tags=["Operations"])
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    # Readiness requires end-to-end auth + list discovery; process health alone doesn't prove it.
    return HealthResponse(status="ok", data_source=settings.data_source, integration_ready=False)


@app.get("/meters", response_model=MeterListResponse, tags=["Meters"])
async def list_meters(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, description="Case-insensitive meter ID or serial search"),
    status: str | None = Query(default=None, description="Exact installation status, case-insensitive"),
    dt_code: str | None = Query(default=None, description="Exact transformer code, case-insensitive"),
    repo: MeterRepository = Depends(get_repository),
) -> MeterListResponse:
    try:
        return await repo.list_meters(limit, offset, search=search, status=status, dt_code=dt_code)
    except (MeterNotFound, PortalAuthenticationRequired, PortalIntegrationPending, UpstreamUnavailable) as exc:
        _raise_api_error(exc)


@app.get("/meters/{meter_id}", response_model=Meter, tags=["Meters"])
async def get_meter(
    meter_id: str = Path(pattern=r"^[A-Za-z0-9-]{1,64}$"),
    repo: MeterRepository = Depends(get_repository),
) -> Meter:
    try:
        return await repo.get_meter(meter_id)
    except (MeterNotFound, PortalAuthenticationRequired, PortalIntegrationPending, UpstreamUnavailable) as exc:
        _raise_api_error(exc)


@app.get("/meters/{meter_id}/location", response_model=LocationResponse, tags=["Meters"])
async def get_location(
    meter_id: str = Path(pattern=r"^[A-Za-z0-9-]{1,64}$"),
    repo: MeterRepository = Depends(get_repository),
) -> LocationResponse:
    try:
        return await repo.get_location(meter_id)
    except (MeterNotFound, PortalAuthenticationRequired, PortalIntegrationPending, UpstreamUnavailable) as exc:
        _raise_api_error(exc)


@app.get("/meters/{meter_id}/consumption", response_model=ConsumptionResponse, tags=["Meters"])
async def get_consumption(
    meter_id: str = Path(pattern=r"^[A-Za-z0-9-]{1,64}$"),
    start: datetime | None = Query(default=None, description="Inclusive timestamp with timezone, ISO 8601"),
    end: datetime | None = Query(default=None, description="Inclusive timestamp with timezone, ISO 8601"),
    repo: MeterRepository = Depends(get_repository),
) -> ConsumptionResponse:
    if start is not None and start.tzinfo is None:
        raise HTTPException(status_code=422, detail="start must include a timezone")
    if end is not None and end.tzinfo is None:
        raise HTTPException(status_code=422, detail="end must include a timezone")
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="start must be before or equal to end")
    try:
        return await repo.get_consumption(meter_id, start, end)
    except (MeterNotFound, PortalAuthenticationRequired, PortalIntegrationPending, UpstreamUnavailable) as exc:
        _raise_api_error(exc)


@app.get("/transformers", response_model=list[TransformerSummary], tags=["Transformers"])
async def list_transformers(settings: Settings = Depends(get_settings)) -> list[TransformerSummary]:
    """Derived solely from the local meter export, NOT the transformer page."""
    try:
        return MeterExportSnapshot(settings.meter_export_path).transformers()
    except (MeterNotFound, PortalIntegrationPending, UpstreamUnavailable) as exc:
        _raise_api_error(exc)


@app.get("/transformers/{dt_code}", response_model=TransformerSummary, tags=["Transformers"])
async def get_transformer(
    dt_code: str = Path(pattern=r"^[A-Za-z0-9-]{1,64}$"),
    settings: Settings = Depends(get_settings),
) -> TransformerSummary:
    try:
        return MeterExportSnapshot(settings.meter_export_path).transformer(dt_code)
    except (MeterNotFound, PortalIntegrationPending, UpstreamUnavailable) as exc:
        _raise_api_error(exc)
