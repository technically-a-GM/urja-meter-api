"""Tests use fictional data, so they never access the real portal."""

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_repository
from app.sample_repository import SampleMeterRepository


@pytest.fixture
def client():
    app.dependency_overrides[get_repository] = lambda: SampleMeterRepository()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_pagination(client):
    response = client.get("/meters?limit=1&offset=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 1
    assert payload["items"][0]["meter_id"] == "DEMO-002"


def test_meter_detail(client):
    response = client.get("/meters/DEMO-001")
    assert response.status_code == 200
    assert response.json()["name"] == "Example North"


def test_missing_meter(client):
    response = client.get("/meters/DOES-NOT-EXIST")
    assert response.status_code == 404


def test_consumption_filter(client):
    response = client.get("/meters/DEMO-001/consumption", params={"start": "2026-01-02T00:00:00Z"})
    assert response.status_code == 200
    assert len(response.json()["readings"]) == 1


def test_rejects_reverse_dates(client):
    response = client.get("/meters/DEMO-001/consumption", params={
        "start": "2026-01-03T00:00:00Z",
        "end": "2026-01-01T00:00:00Z",
    })
    assert response.status_code == 422


def test_openapi_present(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/meters" in response.json()["paths"]
