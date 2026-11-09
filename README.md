# SolarEdge Forecast

SolarEdge Forecast estimates **annual solar energy production** in Home Assistant
using measured production so far plus historical production for the remaining months.

This is a historical production forecast, **not a weather forecast**. You can also
configure a different forecast period, such as July through June. The integration
averages daily production per calendar month across the available
years and interpolates between the middle of adjacent months. Only complete
historical months are used; zero and missing historical readings are excluded.
History must cover every calendar month needed by the calculation, normally
requiring at least a full year of production. Missing history produces an
unavailable sensor rather than an invented estimate.

The sensors show total forecast production, production measured so far, expected
remaining production and progress against the historical baseline, all in kWh.
Additional sensors show the forecast period and production start date. Today's
remaining estimate cannot be negative, even if today's production exceeds its
historical average. Site-local dates and timezone/DST boundaries are used.

**This guide covers V2.0, which requires Home Assistant 2026.11.0 or newer and
SolarEdge Site Access OAuth.**

## Installation

### Install from Home Assistant Marketplace

Marketplace is included in Home Assistant 2026.11 and newer; there is no separate
store integration to install.

1. As a Home Assistant administrator, open **Settings > Marketplace**.
2. Search for **SolarEdge Forecast** or `nelbs/solaredge-forecast` and open its
   repository page. Review the community-content warning when prompted.
3. Review the selected V2 version and select **Install**. Restart Home Assistant if
   Marketplace requests it; restart after updating an existing installation.
4. Follow the setup page, or go to **Settings > Devices & services > Add integration**
   and select **SolarEdge Forecast**. Enter the settings described under
   [Configuration](#configuration), then complete authorization below.

If the repository is not shown in your catalog, use **Settings > Marketplace >
Add from link**, enter `https://github.com/nelbs/solaredge-forecast`, and select
**Add**. Choose **Integration** if asked for a content type. Marketplace may ask
you to connect GitHub when adding a repository from a link.

See the [official Marketplace instructions](https://www.home-assistant.io/integrations/marketplace/)
for version selection and custom repositories.

### Authorize your SolarEdge site

1. Sign in to the [SolarEdge Developer Platform](https://developer.solaredge.com/)
   with your mySolarEdge account. Complete the developer profile and create a
   **Monitoring API / Site Access** application with `SITE_DATA` scope.
   Complete any registration or approval required by SolarEdge. Installer-only
   Fleet Access and Advanced API permissions are not needed.
2. Register a redirect URI under your control. For the manual callback you can use
   `http://localhost:8080/oauth/callback`, or an HTTPS URL you control. Here,
   localhost means **the machine running your browser**, not your Home Assistant
   server. Enter the exact registered redirect URI, client ID and client secret
   into the integration's authorization form.
3. Open the SolarEdge consent link in another tab, sign in, select your configured
   site and approve access.
4. Copy the **complete final URL from the address bar** into the Home Assistant
   callback form. The integration does not run a listener at the redirect URI:
   a connection error or 404 is expected for the localhost example; copy the URL
   anyway. The authorization code is single-use. If authorization fails, open the
   consent link again.
5. Add the forecast sensors to your dashboard.

Enter credentials and callback URLs only in your own Home Assistant instance,
never in chat, issues or screenshots. The callback is processed manually, not by
Home Assistant's automatic OAuth callback. The integration validates the returned
site, redirect URI and any returned `state`/`external_id`; SolarEdge may omit the
latter identifiers, but mismatches are rejected.

### Migration from V1 to V2

**Breaking change:** SolarEdge Forecast V1.0 used SolarEdge Monitoring API V1 with
a **Site API Key** (the legacy `api_key` authentication, labeled "Account key" in
the integration). SolarEdge deprecated and retired Monitoring API V1; the legacy
API has been shut down and its Site API Keys do not work with V2.

SolarEdge Forecast V2.0 uses **Site Access OAuth** instead. Every existing V1
installation needs new authorization; the old account key cannot be converted
into an OAuth grant. This retirement concerns the legacy V1 API, **not** V2's
separate Fleet Access API-key authentication for installers.
See SolarEdge's [Site API Key migration guide](https://api-docs.solaredge.com/docs/developer-platform/6m1ly9bdp9egs-migrating-from-site-api-keys-to-o-auth)
and the [V1-to-V2 API migration guide](https://api-docs.solaredge.com/docs/developer-platform/mxj41549n0nxk-migrating-from-v1-to-v2).

1. Back up Home Assistant and upgrade to **2026.11.0 or newer**.
2. In Marketplace, select the V2 release as described above, install it and restart
   Home Assistant. Installations previously managed by HACS carry over to
   Marketplace automatically with Home Assistant 2026.11.
3. Open the reauthentication request for your existing SolarEdge Forecast entry.
   Register a Site Access application and complete the authorization steps above.
   **Do not delete and recreate the integration.**
4. Check the existing sensors and forecast settings after reauthentication.

The migration retains the config entry, sensor unique IDs, entity customizations,
forecast period and production-start settings, including legacy option-only
settings. The obsolete V1 key is removed after successful reauthentication.
The historical forecast calculation is preserved.

V2 no longer provides V1's `dataPeriod`. If you leave the production start date
blank, history starts with the first full month **after** the site's
`installationDate`. If installation and actual first production differ, set an
explicit production start date to retain the intended history window.

### Configuration

The initial setup and the entry's **Options** form expose the following settings.
Options changes reload the integration.

| Setting | Default | Meaning and restrictions |
|---|---|---|
| Site ID | Required; no default | The numeric ID of your installation in the SolarEdge Monitoring portal. It must match the site selected during authorization. A site cannot be configured twice. Options cannot switch to another site; add a separate integration entry instead. |
| Start day | `1` | First day of the forecast period. Range `1-31`; the day/month combination must be valid in the current year. |
| Start month | `January` | Month of the period's first day. Choose a calendar month; the current or previous year is selected to place the start on or before today. |
| End day | `31` | Last day of the forecast period. Range `1-31`; the day/month combination must be valid in the current year. |
| End month | `December` | Month of the period's last day. The current or next year is selected to place the end on or after today. |
| Production start date | Blank; automatic | Optional date in `DDMMYYYY` format, for example `01012023`. Separators `/` or `-` and spaces are accepted. An explicit date must be at least **365 days in the past**. A first-of-month date includes that month; any other day starts history at the next month. When blank, the month after `installationDate` is used. |
| Update interval | `120` minutes | Refresh production every `60-1440` minutes, inclusive. A longer interval reduces API usage, not the forecast's calculation method. |

The configured period must contain today when you save it. The defaults forecast
the calendar year; a July 1-June 30 period forecasts a year spanning two calendar
years. Period dates are recalculated on every update, including after New Year.
Historical monthly averages use all available complete months in the selected
history window, rather than only the immediately preceding year.

The authorization forms use these additional fields:

| Field | Default | Meaning and restrictions |
|---|---|---|
| Client ID | Required; no initial default | Your SolarEdge Site Access application's client ID. Reauthentication/reconfiguration prefills the saved ID. |
| Client secret | Required; never prefilled | The application's secret. Enter it again when reauthorizing or replacing app credentials. |
| Redirect URI | Required; no initial default | Exactly the URI registered with SolarEdge. HTTPS, or HTTP on `localhost`, `127.0.0.1` or `::1`; no query parameters, fragment or embedded credentials. Reauthentication/reconfiguration prefills the saved URI. |
| Complete callback URL | Required; no default | The final browser URL after consent, containing the code and authorized site ID. Submitted in the separate authorization step. |

Use the entry's **Reconfigure** action to replace app credentials or authorize
again without replacing the sensors. The normal Options form does not edit
credentials. Access tokens last approximately two hours and are refreshed
automatically; every rotated refresh token is saved atomically before further
API use. A failed token write blocks updates until it can be saved.

A refresh token unused for 14 days, a revoked grant or an expired grant requires
authorization again. The integration requests a grant duration of 24 months.
Protect Home Assistant's `.storage` directory and backups: tokens and app
credentials are private local data, **not encrypted credentials**.

## Polling and API calls

| Item | Limit or behavior |
|---|---|
| Integration refresh | Every **120 minutes** by default; configurable from **60 to 1440 minutes** per entry. |
| SolarEdge Free tier | Documented limit of **10 API calls/minute** and **2,000 credits/month**. Limits depend on the SolarEdge plan. Each Monitoring API operation costs one credit. |
| Normal production refresh | **Two Monitoring API calls**: production since the forecast period started, and today's production, both ending at the same current instant. |
| Baseline monthly usage | At 120 minutes, approximately **744 production calls** per 31-day month per site; at the minimum 60 minutes, approximately **1,488**. These are estimates, not quotas, and exclude history, metadata, restarts/manual updates, retries and OAuth traffic. |
| Historical refresh | Complete-month history is cached across restarts and refreshed weekly, at a new month, or when the effective production-start/history window changes. Each history request covers at most **three years** at MONTH resolution; longer history needs multiple calls. Site metadata is fetched when absent from the entry's cache. |
| Request pacing | Requests within an entry, including token refreshes, are spaced at least **6.1 seconds** apart. Multiple entries and other consumers still share the applicable SolarEdge quota. |

OAuth exchanges/refreshes are additional HTTP requests, separate from the two
production operations above; do not treat the baseline estimate as total HTTP
traffic or a guarantee of available credits. Initial setup, historical refreshes
and reauthorization can increase traffic. Marketplace's own update checks are
unrelated to SolarEdge production polling.

On HTTP 429 the integration honors `Retry-After`, with a minimum 60-second
backoff; without a usable header it backs off for an hour. It does not poll more
frequently than configured just because that backoff has elapsed. Network, quota
and malformed-data failures mark sensors unavailable rather than showing stale or
zero production as a successful update. Authentication/permission failures request
reauthentication.

See the [V2 API reference and rate limits](https://github.com/EVWorth/solaredge/blob/main/docs/SE_monitoring_API.md#rate-limits)
and [SolarEdge's homeowner guide](https://api-docs.solaredge.com/docs/developer-platform/df8kx5j4z9vi0-homeowner-and-self-access-guide).

## Changelog

See [changelog.md](changelog.md) for all published releases, including prereleases
and the V2 breaking changes.
