# SolarEdge Forecast

Home Assistant integration forecasting solar production for a configurable period
(January 1 to December 31 by default). The forecast combines **measured production
so far** with **historical production for the remaining calendar months**, not a
weather forecast or an extrapolation of current power.

Version 2 uses Monitoring API V2 through
[`solaredge==3.3.0`](https://pypi.org/project/solaredge/3.3.0/).
V1 keys no longer work. Requires Home Assistant 2026.11 or newer.

## Install and authorize (homeowners)

1. Install with HACS, restart Home Assistant and add **SolarEdge Forecast**.
2. Enter your site ID, forecast period and optional production start date
   (`DDMMYYYY`, also accepting `/` or `-`). The current day must be inside the
   selected period. History must cover every month used by the forecast.
3. Sign in to the [SolarEdge Developer Platform](https://developer.solaredge.com/)
   with your mySolarEdge account. Complete the profile and register a
   **Monitoring API / Site Access** application with `SITE_DATA` scope.
   Installer-only Fleet Access and Advanced API permissions are not needed.
   Complete any SolarEdge-required registration/approval yourself.
4. Register a redirect URI under your control. For a manual callback you can use
   `http://localhost:8080/oauth/callback` (localhost is **your browser's machine**),
   or an HTTPS URL you control. Enter the exact registered URI, client ID and
   client secret in Home Assistant. Never paste credentials into chat,
   screenshots, issues or this repository.
5. Open the consent link in another tab, sign in and authorize the configured
   site. Copy the **complete final address-bar URL** into the callback form.
   There is no built-in listener at the redirect URI: a connection error or 404
   is expected for the localhost example; copy the URL anyway. Codes are
   single-use. If authorization fails, open the consent link again.
6. Add the forecast entities to your dashboard.

The manual callback uses upstream's authorization-code implementation, including
the JSON token endpoint, site binding, registered redirect matching and checks of
returned `state`/`external_id`. SolarEdge may omit these identifiers; because the
URL is submitted manually, missing identifiers are accepted, while mismatches
are rejected. This is not an automatic Home Assistant OAuth callback.

## Upgrade from V1 / renew authorization

Install and restart. Existing entries are upgraded in place and request
**reauthentication**; run the Site Access steps above. Do **not** delete the entry.
Entry IDs, sensor unique IDs, entity registry customizations, forecast dates and
production-start settings remain unchanged, including legacy option-only settings.
The obsolete V1 key is removed after successful reauthentication. App credentials
can also be replaced using **Reconfigure**. The authorized site cannot be changed
in options; add another entry for another site.

Access tokens last approximately two hours. The library serializes refreshes and
retries an unauthorized request once. Every rotated refresh token is saved
immediately to private Home Assistant storage before the API request continues.
Storage is authoritative after restart; rotation does not reload the integration.
A failed write blocks updates until it can be saved. Protect `.storage` and
backups: these are private local files, **not encrypted credentials**.
A refresh token unused for 14 days or an expired/revoked grant requires consent
again (requested grant duration: 24 months).

Authentication/permission failures trigger reauthentication. Network, quota and
malformed-data errors mark sensors unavailable rather than reporting stale or zero
production as success. Retry-After is respected; without it quota failures back
off for an hour. Other consumers can still exhaust your shared app quota.

## Forecast semantics and API budget

The existing calculation is preserved: monthly Wh totals are divided by the
month's actual number of days, averaged across available years per calendar month,
and linearly interpolated between the 15th of adjacent months. Measured production
is added to the remaining estimate; today's remaining estimate cannot be negative.
The progress sensor compares actual production with the historical baseline.
Zero/null historical buckets are excluded as in V1; a missing calendar month
produces an explicit unavailable state, not an invented estimate.

Only complete historical months are used. Without an explicit production start,
V2's `installationDate` determines the first full month **after** installation.
V2 has no V1 `dataPeriod`: if installation and first production differ, set the
production start explicitly to retain your chosen window.
Site-local timezone/DST boundaries are used for queries, buckets and date rollover;
forecast periods are recomputed every update, including after New Year.
Current-production queries stop at the same current instant, not future midnight.
V2 `WH`, `KWH` and `MWH` values are normalized before the original calculation.

Default polling is **120 minutes**, configurable from **60 to 1440** minutes.
Each normal update costs two Basic API calls: period-to-date and today's production.
At the default this is approximately **744 calls per 31-day month per site**,
plus history refreshes and initial metadata. The documented Free tier quota is
2,000 credits/month shared with other applications/consumers.

Complete-month history is cached in storage across restarts and refreshed weekly,
at month rollover or when history settings change. Long history is split into
non-overlapping MONTH windows of at most three years. Site metadata is cached
with history. Changing frequency changes freshness, not forecast methodology.
Requests, including token refreshes, are paced at least 6.1 seconds apart to stay
within 10 calls/minute. Initial history loading can therefore take a little longer.

## Development

```text
python -m venv .venv
# Activate .venv for your platform before running the following commands.
python -m pip install -r requirements-test.txt
python -m pytest -q
python -m ruff check custom_components tests
```

Tests use the real V2 library with mocked HTTP and Home Assistant objects/storage;
no live credentials or credits are required. A live consent and production smoke
test must be performed by the site owner after registering the app.

Contracts: [upstream V2 reference](https://github.com/EVWorth/solaredge/blob/main/docs/SE_monitoring_API.md),
[SolarEdge authentication](https://api-docs.solaredge.com/docs/developer-platform/g09jmvp5t2cok-authentication),
[homeowner self-access guide](https://api-docs.solaredge.com/docs/developer-platform/df8kx5j4z9vi0-homeowner-and-self-access-guide).
