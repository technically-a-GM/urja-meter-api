"""Client for the portal's read-only endpoints."""

import asyncio
import logging
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

import httpx

from app.config import Settings
from app.export_snapshot import MeterExportSnapshot
from app.models import ConsumptionReading, ConsumptionResponse, LocationResponse, Meter, MeterListResponse
from app.repository import MeterNotFound, PortalAuthenticationRequired, PortalIntegrationPending, UpstreamUnavailable
from app.request_signing import build_signed_headers
from app.sveltekit import SveltePayloadError, decode_meter_detail

METER_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,64}$")
logger = logging.getLogger(__name__)


def _optional_number(value: Any) -> float | None:
    """Convert valid finite numeric readings; treat missing/error markers as absent."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value.strip().replace(",", "") if isinstance(value, str) else value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _reading_timestamp(value: Any, tz: ZoneInfo) -> datetime:
    """Parse the portal's day-first timestamps; attach the documented assumed timezone."""
    if not isinstance(value, str):
        raise ValueError("Missing reading timestamp")
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError("Unrecognized reading timestamp")


class UrjaPortalClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._transport = transport  # allows deterministic tests with MockTransport
        self._session_cookie = settings.portal_session_cookie.strip()
        # Avoid simultaneous logins when multiple API requests encounter an expired session.
        self._login_lock = asyncio.Lock()

    def _can_login(self) -> bool:
        return bool(self.settings.portal_email and self.settings.portal_password)

    def _http_client(self, cookie: str = "") -> httpx.AsyncClient:
        headers = {
            "Accept": "application/json",
            "User-Agent": "UrjaMeterAPI/0.8 (operator-authorized read-only adapter)",
        }
        if cookie:
            headers["Cookie"] = cookie
        return httpx.AsyncClient(
            base_url=self.settings.portal_base_url.rstrip("/"),
            headers=headers,
            timeout=self.settings.upstream_timeout_seconds,
            follow_redirects=False,
            transport=self._transport,
        )

    async def _login(self, *, failed_cookie: str | None = None) -> None:
        """Log in with the observed HTML form; keep only session cookies in memory.

        failed_cookie avoids duplicate logins when another coroutine already renewed
        the session while this request was in flight. Never log credentials/cookies.
        """
        if not self._can_login():
            raise PortalAuthenticationRequired(
                "Portal session expired; configure PORTAL_EMAIL and PORTAL_PASSWORD locally for automatic renewal"
            )
        async with self._login_lock:
            if failed_cookie is not None and self._session_cookie != failed_cookie and self._session_cookie:
                return
            try:
                async with self._http_client() as client:
                    # Match the login form request made by the website.
                    origin = self.settings.portal_base_url.rstrip("/")
                    response = await client.post(
                        "/login",
                        files={
                            "email": (None, self.settings.portal_email),
                            "password": (None, self.settings.portal_password),
                        },
                        headers={
                            "Accept": "application/json",
                            "x-sveltekit-action": "true",
                            "Origin": origin,
                            "Referer": f"{origin}/login",
                        },
                    )
            except httpx.RequestError as exc:
                raise UpstreamUnavailable("Cannot reach upstream portal login") from exc
            if response.status_code not in {200, 302, 303}:
                if response.status_code == 403:
                    reason = "request forbidden (check form origin/CSRF and account access)"
                elif response.status_code in {400, 401, 422}:
                    reason = "form rejected (verify account details and request format)"
                else:
                    reason = "unexpected response"
                raise PortalAuthenticationRequired(
                    f"Portal login failed: HTTP {response.status_code}, {reason}"
                )
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError as exc:
                    raise PortalAuthenticationRequired(
                        "Portal login returned non-JSON data; enhanced form action may be unsupported"
                    ) from exc
                if not isinstance(body, dict):
                    raise PortalAuthenticationRequired("Unexpected portal login response shape")
                if body.get("type") != "redirect" or body.get("status") != 303 or body.get("location") != "/meters":
                    action_status = body.get("status")
                    if isinstance(action_status, int) and 400 <= action_status <= 499:
                        raise PortalAuthenticationRequired(f"Portal login form rejected: action status {action_status}")
                    raise PortalAuthenticationRequired("Portal did not confirm a successful login")
            else:
                location = response.headers.get("location", "")
                if location not in {"/meters", "/"}:
                    raise PortalAuthenticationRequired("Portal login redirected unexpectedly")
            cookies = dict(response.cookies.items())
            if not cookies or not any(name.endswith("session_token") for name in cookies):
                raise PortalAuthenticationRequired("Portal login did not establish a session cookie")
            self._session_cookie = "; ".join(f"{name}={value}" for name, value in cookies.items())

    async def _ensure_auth(self) -> None:
        if not self._session_cookie:
            if not self._can_login():
                raise PortalAuthenticationRequired(
                    "No portal session configured. Set PORTAL_EMAIL and PORTAL_PASSWORD locally, or provide PORTAL_SESSION_COOKIE."
                )
            await self._login(failed_cookie="")

    @staticmethod
    def _validate_id(meter_id: str) -> None:
        if not METER_ID_PATTERN.fullmatch(meter_id):
            raise MeterNotFound(meter_id)

    async def _get_json(
        self, path: str, *, params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        await self._ensure_auth()
        # Retry an unauthorized request only once.
        for attempt in range(2):
            cookie_used = self._session_cookie
            try:
                async with self._http_client(cookie_used) as client:
                    response = await client.get(path, params=params, headers=extra_headers)
            except httpx.RequestError as exc:
                raise UpstreamUnavailable("Cannot reach upstream portal") from exc
            if response.status_code in {401, 302, 303, 307, 308}:
                if attempt == 0 and self._can_login():
                    await self._login(failed_cookie=cookie_used)
                    continue
                raise PortalAuthenticationRequired("Portal session rejected or expired")
            if response.status_code == 403:
                raise PortalAuthenticationRequired("Upstream request forbidden; check session and permissions")
            if response.status_code == 404:
                raise MeterNotFound("Upstream record not found")
            if response.status_code >= 400:
                raise UpstreamUnavailable(f"Upstream responded with HTTP {response.status_code}")
            try:
                if "json" not in response.headers.get("content-type", "").lower():
                    raise ValueError("Non-JSON upstream response (possibly login page)")
                return response.json()
            except ValueError as exc:
                raise UpstreamUnavailable("Unexpected upstream response format") from exc
        raise PortalAuthenticationRequired("Portal session rejected or expired")

    async def fetch_export(self) -> list[dict[str, Any]]:
        """Read the confirmed export endpoint (with bounded pagination).

        Browser inspection confirmed GET /portal/export?page=1 and its JSON
        response {"data": [...], "total": 403}. The first page may contain all
        records; if it does not, follow the same ``page`` query parameter until
        ``total`` records have been collected. Never guess a page size.
        """
        key_payload = await self._get_json("/portal/keys")
        key_data = key_payload.get("data") if isinstance(key_payload, dict) else None
        secret = key_data.get("signingSecret") if isinstance(key_data, dict) else None
        if not isinstance(secret, str) or not secret:
            raise UpstreamUnavailable("Portal did not return valid export signing information")

        records: list[dict[str, Any]] = []
        expected_total: int | None = None
        seen: set[str] = set()
        max_pages = 50
        max_records = 10000
        for page in range(1, max_pages + 1):
            # Sign the same query string sent in this request.
            query = f"page={page}"
            signed = build_signed_headers("GET", "/portal/export", query, secret)
            payload = await self._get_json(
                "/portal/export", params={"page": str(page)}, extra_headers=signed,
            )
            if not isinstance(payload, dict):
                raise UpstreamUnavailable("Unexpected export response: expected an object")
            data, total = payload.get("data"), payload.get("total")
            if not isinstance(data, list) or type(total) is not int or not 0 <= total <= max_records:
                raise UpstreamUnavailable("Unexpected export response: invalid data or total")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise UpstreamUnavailable("Export total changed while downloading; retry later")
            if not data and len(records) < total:
                raise UpstreamUnavailable("Export returned an empty page before completion")
            for row in data:
                if not isinstance(row, dict) or not isinstance(row.get("meterId"), str) or not row["meterId"].strip():
                    raise UpstreamUnavailable("Export contains an invalid meter record")
                meter_id = row["meterId"]
                if meter_id in seen:
                    raise UpstreamUnavailable("Export contains duplicate meter IDs across pages")
                seen.add(meter_id)
                records.append(row)
            if len(records) > total:
                raise UpstreamUnavailable("Export has more records than the declared total")
            if len(records) == total:
                return records
        raise UpstreamUnavailable("Export exceeded the configured page limit")

    async def list_meters(
        self, limit: int, offset: int, search: str | None = None,
        status: str | None = None, dt_code: str | None = None,
    ) -> MeterListResponse:
        return MeterExportSnapshot(self.settings.meter_export_path).list_meters(
            limit, offset, search=search, status=status, dt_code=dt_code
        )

    async def get_location(self, meter_id: str) -> LocationResponse:
        self._validate_id(meter_id)
        payload = await self._get_json(f"/portal/meters/{meter_id}/geo")
        try:
            coords = payload["data"]
            latitude = float(coords["latitude"]) if coords.get("latitude") not in (None, "") else None
            longitude = float(coords["longitude"]) if coords.get("longitude") not in (None, "") else None
            return LocationResponse(meter_id=meter_id, latitude=latitude, longitude=longitude)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise UpstreamUnavailable("Unexpected upstream geo data") from exc

    async def get_meter(self, meter_id: str) -> Meter:
        self._validate_id(meter_id)
        payload = await self._get_json(
            f"/meters/{meter_id}/__data.json", params={"x-sveltekit-invalidated": "001"}
        )
        try:
            root = decode_meter_detail(payload)
            detail_list = root["detail"]["data"]
            nameplate = {row["parameterName"]: row.get("parameterValue") for row in detail_list}
            hierarchy = root.get("hierarchy") or {}
            portal_id = str(root["meterId"])
            if portal_id != meter_id:
                raise ValueError("Meter ID mismatch in portal response")
        except (SveltePayloadError, KeyError, TypeError, ValueError) as exc:
            raise UpstreamUnavailable("Could not decode SvelteKit meter detail") from exc

        # Some meters may lack coordinates. Preserve their details in that case.
        try:
            location = await self.get_location(meter_id)
        except MeterNotFound:
            location = LocationResponse(meter_id=meter_id)
        return Meter(
            meter_id=portal_id,
            status=nameplate.get("Installation Status"),
            latitude=location.latitude,
            longitude=location.longitude,
            attributes={
                "serial_number": nameplate.get("Serial No"),
                "make": nameplate.get("Make"),
                "phase_type": nameplate.get("Phase Type"),
                "installation_type": nameplate.get("Installation Type"),
                "hierarchy": hierarchy,
            },
        )

    async def get_consumption(
        self,
        meter_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ConsumptionResponse:
        self._validate_id(meter_id)
        payload = await self._get_json(f"/portal/meters/{meter_id}/energy")
        try:
            tz = ZoneInfo(self.settings.portal_timezone)
        except ZoneInfoNotFoundError as exc:
            raise UpstreamUnavailable(
                "Timezone data is unavailable; run 'python -m pip install tzdata' and restart the server"
            ) from exc

        records = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise UpstreamUnavailable("Unexpected upstream energy data: expected a data array")

        readings = []
        skipped = 0
        for entry in records:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            try:
                parsed = _reading_timestamp(entry.get("timestamp"), tz)
            except ValueError:
                skipped += 1
                continue
            kwh = _optional_number(entry.get("kwh"))
            if kwh is None:
                skipped += 1
                continue
            readings.append(ConsumptionReading(
                timestamp=parsed,
                timestamp_original=entry["timestamp"],
                kwh=kwh,
                kvah=_optional_number(entry.get("kvah")),
                voltage_r=_optional_number(entry.get("voltR")),
            ))

        if records and not readings:
            raise UpstreamUnavailable(
                "Upstream energy data contains no valid timestamp/kWh records"
            )
        if skipped:
            logger.warning("Skipped %d malformed energy records for meter %s", skipped, meter_id)
        if start is not None:
            readings = [r for r in readings if r.timestamp >= start]
        if end is not None:
            readings = [r for r in readings if r.timestamp <= end]
        return ConsumptionResponse(meter_id=meter_id, readings=readings, skipped_records=skipped)
