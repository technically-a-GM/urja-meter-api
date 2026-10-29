"""Read-only local catalog from the portal's authorized bulk JSON download.

The export route has been confirmed by DevTools and can be fetched with
the explicit scripts.refresh_export command using an authorized session.
The export is NOT packaged in public source.
"""

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models import Meter, MeterListResponse, TransformerSummary
from app.repository import MeterNotFound, PortalIntegrationPending, UpstreamUnavailable


def _required_string(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing/invalid {field}")
    return value.strip()


def _meter_from_export(row: dict[str, Any]) -> Meter:
    meter_id = _required_string(row, "meterId")
    hierarchy = row.get("hierarchy")
    geo = row.get("geo")
    if not isinstance(hierarchy, dict) or not isinstance(geo, dict):
        raise ValueError(f"{meter_id}: hierarchy or geo is not an object")
    # Preserve source hierarchy verbatim, including blanks and conflicting names.
    # No location or other values are invented when missing.
    latitude = geo.get("lat")
    longitude = geo.get("lng")
    try:
        latitude = None if latitude in (None, "") else float(latitude)
        longitude = None if longitude in (None, "") else float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{meter_id}: invalid coordinates") from exc
    return Meter(
        meter_id=meter_id,
        status=row.get("installStatus"),
        latitude=latitude,
        longitude=longitude,
        attributes={
            "serial_number": row.get("serialNo"),
            "make": row.get("make"),
            "phase_type": row.get("phaseType"),
            "installation_type": row.get("installType"),
            "dt_code": row.get("dtCode"),
            "source_build": row.get("build"),
            "hierarchy": hierarchy,
        },
    )


@lru_cache(maxsize=8)
def _cached_export(path: str, mtime_ns: int, size: int) -> tuple[Meter, ...]:
    """Reload automatically if file changes (mtime and size are cache keys)."""
    try:
        with open(path, encoding="utf-8") as fp:
            rows = json.load(fp)
        if not isinstance(rows, list):
            raise ValueError("export must be a top-level JSON array")
        meters = tuple(_meter_from_export(row) for row in rows)
        ids = [m.meter_id for m in meters]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate meterId values in export")
        return meters
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise UpstreamUnavailable(f"Could not parse local meter export: {exc}") from exc


class MeterExportSnapshot:
    def __init__(self, path: str):
        self.path = Path(path)

    def meters(self) -> tuple[Meter, ...]:
        if not self.path.is_file():
            raise PortalIntegrationPending(
                "Meter catalog requires a local export. Download 'Export all meters' "
                "from the authorized portal and save it as data/meter-export.json."
            )
        try:
            stat = self.path.stat()
        except OSError as exc:
            raise UpstreamUnavailable("Cannot read local export metadata") from exc
        return _cached_export(str(self.path.resolve()), stat.st_mtime_ns, stat.st_size)

    def list_meters(
        self,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        dt_code: str | None = None,
    ) -> MeterListResponse:
        meters = self.meters()
        if search:
            q = search.casefold().strip()
            meters = tuple(m for m in meters if q in m.meter_id.casefold()
                           or q in str(m.attributes.get("serial_number") or "").casefold())
        if status:
            meters = tuple(m for m in meters if (m.status or "").casefold() == status.strip().casefold())
        if dt_code:
            meters = tuple(m for m in meters if str(m.attributes.get("dt_code") or "").casefold() == dt_code.strip().casefold())
        return MeterListResponse(items=list(meters[offset:offset + limit]), total=len(meters), limit=limit, offset=offset)

    def transformers(self) -> list[TransformerSummary]:
        # Reconstruct from meter references only. Upstream transformer capacity
        # is NOT in this export and must not be invented.
        grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"names": set(), "feeders": set(), "meter_count": 0})
        for meter in self.meters():
            code = str(meter.attributes.get("dt_code") or "").strip()
            if not code:
                continue
            dt = meter.attributes["hierarchy"].get("dt") or {}
            feeder = meter.attributes["hierarchy"].get("feeder") or {}
            entry = grouped[code]
            entry["meter_count"] += 1
            if isinstance(dt, dict) and dt.get("name"):
                entry["names"].add(str(dt["name"]))
            if isinstance(feeder, dict) and feeder.get("code"):
                entry["feeders"].add(str(feeder["code"]))
        return [TransformerSummary(
            code=code,
            name=sorted(entry["names"])[0] if len(entry["names"]) == 1 else None,
            name_variants=sorted(entry["names"]),
            feeder_codes=sorted(entry["feeders"]),
            meter_count=entry["meter_count"],
            capacity_kva=None,
        ) for code, entry in sorted(grouped.items())]

    def transformer(self, code: str) -> TransformerSummary:
        for dt in self.transformers():
            if dt.code.casefold() == code.casefold():
                return dt
        raise MeterNotFound(code)
