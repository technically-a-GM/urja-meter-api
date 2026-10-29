# Portal notes

These requests were observed in Chrome DevTools while using a regular logged-in account. All integration calls after login are read-only.

## Login

`POST /login` sends multipart form fields named `email` and `password`. The SvelteKit form request also uses `x-sveltekit-action: true` and same-origin headers. A successful login returned HTTP 200 with:

```json
{"type":"redirect","status":303,"location":"/meters"}
```

The response sets a `__Secure-better-auth.session_token` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`; observed `Max-Age=3600`). The client holds the cookie in memory and retries a read once after HTTP 401. Other failures are returned as API errors. No real cookie values are recorded here.

## Meter endpoints

| Request | Response |
| --- | --- |
| `GET /meters/{id}/__data.json?x-sveltekit-invalidated=001` | Indexed SvelteKit node data: meter nameplate and hierarchy |
| `GET /portal/meters/{id}/geo` | `{ "data": { "latitude": "...", "longitude": "..." } }` |
| `GET /portal/meters/{id}/energy` | `{ "data": [{"timestamp":"...","kwh":"...","kvah":"...","voltR":"..."}] }` |
| `GET /portal/dts?page=1` | Transformer list (observed in site JavaScript) |
| `GET /portal/export?page=1` | Bulk meter rows and `total` count |

For the meter detail response, `nodes[*].data` contains a flat array. Some objects store integer references to other elements in that array. The converter in `sveltekit.py` handles the shape seen for the meter detail page.

Example energy row:

```json
{"timestamp":"23/06/2026 23:30","kwh":"42594.05","kvah":"46001.58","voltR":"231"}
```

The timestamps are day-first and have no timezone. `Asia/Kolkata` is assumed, and the original string is retained in the API response. The values appear to be meter registers (cumulative).

## Bulk export

Clicking **Export all meters** on `/transformers` sends `GET /portal/keys` followed by `GET /portal/export?page=1`. The second request includes `X-Timestamp` and `X-Signature`.

The request signature was observed in the portal's JavaScript:

```text
message = "GET\n/portal/export\npage=1\n<unix timestamp seconds>"
signature = HMAC-SHA256(signing_secret, message).hexdigest()
```

The signing secret comes from the authenticated `/portal/keys` response. It is used in memory only. The export returns `{ "data": [...], "total": 403 }` for the inspected dataset; the downloaded JSON file is just the array under `data`.

The Python refresh command signs each page, validates unique meter IDs and required fields, then replaces the local JSON file. If downloading or validation fails, it keeps the old file.

## Export observations

The downloaded file had 403 records and 403 unique IDs. Each row included `meterId`, `serialNo`, `make`, `phaseType`, `installStatus`, `installType`, `dtCode`, `build`, `hierarchy`, and `geo`. There were 40 distinct `dtCode` values.

Some hierarchy codes are empty. `DT-007` appeared under both `Sanganer DT 7` and `Old Malviya Nagar Xfmr`. The API preserves conflicting names rather than selecting one. The export has no transformer-capacity field, even though capacities appear on the website.

## API mapping

`GET /meters` and `/transformers` use the local export snapshot. `GET /meters/{id}`, `/location` and `/consumption` call the portal directly. The catalog is therefore only as recent as the last refresh, while individual records are live.

**Not investigated fully:** how portal-side meter search is paginated, differences between `legacy` and `v2` records, and the timezone used by the source system. A live expiry/renewal test over a full session lifetime would also be useful.
