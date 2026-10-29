import hashlib
import hmac

import httpx
import pytest

from app.config import Settings
from app.portal_client import UrjaPortalClient


def client_with(handler, cookie=""):
    settings = Settings(
        data_source="live", portal_email="operator@example.invalid",
        portal_password="test-password", portal_session_cookie=cookie,
        _env_file=None,
    )
    return UrjaPortalClient(settings, transport=httpx.MockTransport(handler))


def login_response():
    return httpx.Response(
        200, json={"type": "redirect", "status": 303, "location": "/meters"},
        headers={"set-cookie": "__Secure-better-auth.session_token=test-cookie; Path=/; HttpOnly; Secure"},
    )


@pytest.mark.asyncio
async def test_login_and_location_request():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/login":
            assert request.method == "POST"
            assert request.headers["content-type"].startswith("multipart/form-data")
            assert b'name="email"' in request.content
            assert b'name="password"' in request.content
            return login_response()
        assert request.headers["cookie"] == "__Secure-better-auth.session_token=test-cookie"
        return httpx.Response(200, json={"data": {"latitude": "26.8", "longitude": "75.9"}})

    result = await client_with(handler).get_location("J100001")
    assert result.latitude == 26.8
    assert calls == ["/login", "/portal/meters/J100001/geo"]


@pytest.mark.asyncio
async def test_expired_session_logs_in_again():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/login":
            return login_response()
        if request.headers.get("cookie") == "expired=1":
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"data": {"latitude": "26.8", "longitude": "75.9"}})

    assert (await client_with(handler, cookie="expired=1").get_location("J100001")).longitude == 75.9
    assert calls == ["/portal/meters/J100001/geo", "/login", "/portal/meters/J100001/geo"]


@pytest.mark.asyncio
async def test_signed_export():
    def handler(request):
        if request.url.path == "/login":
            return login_response()
        if request.url.path == "/portal/keys":
            return httpx.Response(200, json={"data": {"signingSecret": "test-key"}})
        assert request.url.path == "/portal/export"
        timestamp = request.headers["x-timestamp"]
        message = f"GET\n/portal/export\npage=1\n{timestamp}".encode()
        expected = hmac.new(b"test-key", message, hashlib.sha256).hexdigest()
        assert request.headers["x-signature"] == expected
        return httpx.Response(200, json={"data": [], "total": 0})

    assert await client_with(handler).fetch_export() == []
