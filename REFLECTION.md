# Reflection

## Assumptions

I assumed the reading timestamps were in Indian time because the source returned a date and time without an offset. I also treated kWh/kVAh as cumulative readings rather than half-hourly usage. I left missing hierarchy values unchanged instead of guessing them.

## Hardest part

The export request was the most difficult part. A normal GET worked for meter location, but the export returned 401. I compared the requests in Chrome DevTools and found that the export used timestamp and signature headers. Looking at the site's JavaScript helped me understand the HMAC signing step.

## What I would improve with another day

I would test session renewal after a real timeout, add a last-refreshed timestamp for the catalog, and investigate getting transformer capacity directly from the portal rather than leaving it null.

## A mistake I made

I first thought the 401 response meant the session had expired. The location request still worked with the same cookie, so the actual issue was that the export needed signed headers. Later, the Python login also needed the same form request format as the browser.

## What I would criticise in this submission

The meter list relies on a snapshot and does not update automatically. Consumption timestamps use an assumed timezone, and the API has no separate access control for its consumers. I would address those before deploying this beyond a local engineering tool.
