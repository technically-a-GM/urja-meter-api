"""Refresh local catalog from confirmed read-only Urja bulk endpoint.

Run: python -m scripts.refresh_export
Requires either PORTAL_EMAIL and PORTAL_PASSWORD, or PORTAL_SESSION_COOKIE in local .env (not committed).
Fetches a short-lived signing key only through authorized GET /portal/keys.
"""

import asyncio
import sys
from pathlib import Path

from app.bulk_refresh import refresh_snapshot
from app.config import get_settings
from app.portal_client import UrjaPortalClient
from app.repository import PortalAuthenticationRequired, UpstreamUnavailable, MeterNotFound


async def main() -> None:
    settings = get_settings()
    if settings.data_source != "live":
        raise ValueError("Set DATA_SOURCE=live in your local .env before refreshing")
    count = await refresh_snapshot(
        UrjaPortalClient(settings), Path(settings.meter_export_path)
    )
    print(f"Refreshed {count} meters in {settings.meter_export_path}")
    print("GET /meters and GET /transformers will use the refreshed snapshot.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, PortalAuthenticationRequired, UpstreamUnavailable, MeterNotFound) as exc:
        # Our exception messages intentionally contain no cookies or raw responses.
        print(f"Refresh failed: {exc}", file=sys.stderr)
        sys.exit(1)
