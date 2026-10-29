# Urja Meter API

A read-only FastAPI service for accessing data from the Urja Meter Ops portal. It provides meter details, energy readings, a searchable meter list and basic transformer information.

## Setup

Requires Python 3.11+. In Windows CMD, from this folder:

```cmd
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
copy .env.example .env
```

In `.env`, change `DATA_SOURCE` to `live` and set `PORTAL_EMAIL` and `PORTAL_PASSWORD` using the account supplied for the assignment. Keep `PORTAL_SESSION_COOKIE` empty for automatic login. Do not commit `.env`.

```cmd
python -m scripts.refresh_export
python -m uvicorn app.main:app --reload
```

The first command downloads the meter list to `data/meter-export.json`. The second runs the API at <http://127.0.0.1:8000/docs>. If you only want to try the API without portal access, leave `DATA_SOURCE=sample` and start Uvicorn without running the refresh command.

## Endpoints

| Route | Purpose |
| --- | --- |
| `GET /meters?limit=10&offset=0` | Meter list with pagination |
| `GET /meters?search=J100001` | Search by meter ID or serial number |
| `GET /meters?status=Faulty&dt_code=DT-002` | Filter by status and transformer |
| `GET /meters/{meter_id}` | Meter details and hierarchy |
| `GET /meters/{meter_id}/location` | Latitude and longitude |
| `GET /meters/{meter_id}/consumption` | Energy readings, optional `start` and `end` |
| `GET /transformers` | Transformers derived from the meter list |
| `GET /transformers/{dt_code}` | One transformer summary |
| `GET /health` | Basic process status |

Example:

```http
GET http://127.0.0.1:8000/meters/J100001/consumption
```

The response contains timestamped kWh, kVAh and R-phase voltage readings. For date filtering, supply ISO 8601 timestamps with an offset, such as `2026-06-24T00:00:00+05:30`.

`openapi.json` contains the OpenAPI specification. To regenerate it after changing the routes:

```cmd
python -m scripts.export_openapi
```

## How it works

- `portal_client.py` handles login and the live meter requests through HTTPX. It keeps the session cookie in memory and tries logging in again once after a `401` response.
- The portal's detail page uses an indexed SvelteKit JSON format. `sveltekit.py` converts the observed format into a normal Python dictionary.
- The bulk export requires a signed request. `request_signing.py` generates its HMAC-SHA256 headers; the signing key is obtained during the authorized session, not stored in the project.
- `export_snapshot.py` serves search and pagination from the downloaded JSON. It also groups meters by transformer code.

The catalog is a **local snapshot**, refreshed only when `python -m scripts.refresh_export` runs. Meter details, coordinates and energy readings are fetched live. The original export contained 403 meters and 40 transformer codes when inspected; these numbers can change.

## Tests

```cmd
python -m pytest -q
```

Tests use fictional records and mocked HTTP responses. They do not contact the real portal.

## Assumptions and limitations

- The portal's reading timestamps do not include a timezone. The API currently assumes `Asia/Kolkata`.
- kWh/kVAh appear to be cumulative register values, not usage per 30-minute interval.
- Some hierarchy codes are blank and one transformer code has conflicting names. The API leaves these as they appear in the source.
- Transformer capacity is shown on the portal page but is not present in the meter export. The derived transformer endpoint returns `null` for it.
- There is no automatic scheduled catalog refresh, and the local API does not authenticate its own callers. Keep it on localhost.

`PROTOCOL.md` records the portal requests and response formats. `REFLECTION.md` covers the decisions, problems and remaining work.

## Files

- `app/` — API routes, data models, portal client, parsing and export handling
- `scripts/` — refresh the catalog or regenerate OpenAPI
- `tests/` — a small offline test suite
- `data/` — local snapshot (excluded from Git)

Only source and documentation belong in a public repository. Do **not** upload `.env`, downloaded meter data, session cookies or signing keys.
