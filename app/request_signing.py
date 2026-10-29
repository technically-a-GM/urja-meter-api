"""Observed Urja export signature algorithm.

The portal browser computes HMAC-SHA256 over the UTF-8 bytes of
``METHOD\nPATH\nQUERY\nUNIX_SECONDS``. Never store or print the signing key.
"""

import hashlib
import hmac
import time


def build_signed_headers(
    method: str, path: str, query: str, signing_secret: str,
    *, timestamp: int | None = None,
) -> dict[str, str]:
    """Create the browser-compatible export headers with a fresh timestamp.

    ``query`` must be exactly the raw query string sent in the HTTP request,
    without a leading '?' (for example ``page=1``).
    """
    if not isinstance(signing_secret, str) or not signing_secret:
        raise ValueError("Missing export signing key")
    if timestamp is None:
        timestamp = int(time.time())
    timestamp_str = str(timestamp)
    signed_text = "\n".join((method, path, query, timestamp_str))
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        signed_text.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"x-timestamp": timestamp_str, "x-signature": digest}
