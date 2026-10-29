"""Explicit, read-only bulk refresh with validation and atomic replacement.

Never expose this as an unauthenticated API route: it reads private meter data
and deliberately contacts the upstream service. Run it as an operator command.
"""

import json
import os
import tempfile
from pathlib import Path

from app.export_snapshot import _meter_from_export
from app.portal_client import UrjaPortalClient
from app.repository import UpstreamUnavailable


async def refresh_snapshot(client: UrjaPortalClient, target: Path) -> int:
    """Fetch complete confirmed export, validate and atomically replace snapshot.

    An upstream/auth/schema error must never overwrite the prior good snapshot.
    """
    records = await client.fetch_export()
    try:
        ids: set[str] = set()
        for record in records:
            meter = _meter_from_export(record)
            if meter.meter_id in ids:
                raise ValueError("duplicate meterId")
            ids.add(meter.meter_id)
    except (TypeError, KeyError, ValueError) as exc:
        raise UpstreamUnavailable("Export validation failed; existing snapshot was kept") from exc

    target = Path(target)
    temporary: str | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".tmp", prefix=".meter-export-",
            dir=target.parent, delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        raise UpstreamUnavailable("Unable to save refreshed snapshot; check local file permissions") from exc
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return len(records)
