# Changelog

All releases, including prereleases, are listed below in reverse
chronological order. Historical entries were reconstructed from
[GitHub releases](https://github.com/nelbs/solaredge-forecast/releases),
their tags and the changes between those tags. Dates are GitHub publication
dates in UTC, not commit dates. Early release notes were sparse; the summaries
below describe only changes supported by the release title, notes or code.

## [2.0.1-beta.1](https://github.com/nelbs/solaredge-forecast/releases/tag/2.0.1-beta.1) - 2026-11-11

- Fix V2 setup failing when `installationDate` contains an ISO timestamp such as
  `2022-12-14T00:00:00Z`. Accept ISO dates and timestamps in the shared
  installation/history date parser while preserving the supplied calendar date.

## [2.0.0](https://github.com/nelbs/solaredge-forecast/releases/tag/2.0.0) - 2026-11-09

**Stable V2 release. Breaking changes from V1:**

- Replace the retired SolarEdge Monitoring API V1 **Site API Key** authentication
  with V2 **Site Access OAuth**. Register a Site Access application and complete
  reauthentication; V1 keys cannot be reused.
- Require **Home Assistant 2026.11.0 or newer**.
- Retain existing entries, sensor identities and user settings during
  reauthentication. Do not delete and recreate the integration.
- Default refresh is now **120 minutes**, configurable from **60 to 1440 minutes**.
- Without an explicit production start, use the first complete month after
  V2's `installationDate` rather than V1's unavailable `dataPeriod`.
- Network, quota and invalid-data failures mark sensors unavailable rather than
  presenting cached results as a successful update.

**Included improvements:**

- Promote the V2 implementation tested in 2.0.0-beta.1, with rotating OAuth tokens
  persisted atomically, historical-month caching, rate-limit pacing/backoff and
  timezone-aware V2 production mapping.
- Preserve the forecast based on measured production plus historical production
  for the remaining months.
- Rewrite the README with Marketplace installation, V1-to-V2 migration,
  configuration fields and polling/API-budget guidance.
- Add this retrospective changelog.

The site owner confirmed the beta works with their installation before this
stable release. The implementation is covered by 46 automated tests; this is not
a claim that every SolarEdge site or configuration has been live-tested.

## [2.0.0-beta.1](https://github.com/nelbs/solaredge-forecast/releases/tag/2.0.0-beta.1) - 2026-11-09

**Prerelease. Breaking changes:**

- Replace SolarEdge Monitoring API V1 with V2 through `solaredge==3.3.0`.
  Old V1 API keys no longer work. Homeowners must register a Site Access
  application and reauthorize through the manual OAuth callback flow.
- Require **Home Assistant 2026.11.0 or newer**.
- Change default polling from 15 to **120 minutes**, configurable from
  **60 to 1440 minutes**, to reduce V2 credit usage.
- When no production start is configured, replace V1's unavailable `dataPeriod`
  lookup with the first complete month after V2's `installationDate`. Set an
  explicit production start if the dates differ.
- Report network, quota and invalid-data failures as unavailable instead of
  presenting the previous successful forecast as a successful new update.

**Added and changed:**

- Migrate entries in place, retaining sensor identities and user settings.
- Manage access-token expiry and rotating refresh tokens, persist rotations
  atomically in private storage and support reauthentication/reconfiguration.
- Map V2 energy units and timezone-aware queries to the existing historical
  forecast calculation; recompute forecast periods at date/year rollover.
- Cache completed historical months across restarts, refresh weekly/on month
  rollover/history-setting changes, and split long history into three-year queries.
- Pace requests and honor rate-limit backoff.
- Add 46 focused tests, CI checks, updated translations and setup documentation.

The original release notes recorded live validation as outstanding at publication.
The site owner subsequently confirmed on **2026-11-09** that the beta works with
their installation; that confirmation does not imply validation of every site or
configuration.

## [1.0.6-beta.4](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.6-beta.4) - 2026-06-28

**Prerelease.**

- Redact SolarEdge API keys from API errors before they reach Home Assistant logs.
- Wrap library exceptions without chaining the original exception, preventing
  API-key-bearing URLs from appearing in the integration's tracebacks.
- Retain the transient-error fallback introduced in beta.3.

## [1.0.6-beta.3](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.6-beta.3) - 2026-06-28

**Prerelease.**

- Keep the previous successful forecast on transient API failures such as
  429, 502/503/504 and timeouts.
- Redact API keys in coordinator update-error logs.
- Initial failures without previous data can still leave sensors unavailable.

## [1.0.6-beta.2](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.6-beta.2) - 2026-06-27

**Prerelease.**

- Fix configuration-schema serialization by removing an unserializable lambda.
- Add validation messaging for a missing API key.
- Retain compatibility fallbacks for older Home Assistant setup, unload and
  coordinator APIs.

## [1.0.6-beta.1](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.6-beta.1) - 2026-06-27

**Prerelease.**

- Fix config-flow loading by lazily importing the forecast client.
- Improve configuration/options validation and coordinator setup/unload handling.
- Replace pandas/dateutil forecast calculations with pure-Python helpers.
- Use a beta version above the latest stable 1.0.5 release.

## [1.0.5](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.5) - 2025-07-10

- Revert the options-flow constructor change made in 1.0.4.

## [1.0.4](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.4) - 2025-07-10

- Change options-flow initialization in preparation for a Home Assistant
  deprecation. This constructor change was reverted in 1.0.5.
- Include the Portuguese translation added since 1.0.3.

## [1.0.3](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.3) - 2024-12-24

- Replace the deprecated `ENERGY_KILO_WATT_HOUR` constant with
  `UnitOfEnergy.KILO_WATT_HOUR`.

## [1.0.2](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.2) - 2024-05-02

- Declare `solaredge==0.0.4` in the integration manifest.
- Include validation-workflow and README updates made since 1.0.1.

## [1.0.1](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.1) - 2024-01-09

- Publish the release titled "Add to HACS" and update the manifest version.
  HACS was the installation channel at that time.
- Apply a formatting correction in the forecast calculation.

## [1.0.0](https://github.com/nelbs/solaredge-forecast/releases/tag/1.0.0) - 2024-01-09

- Publish the first stable release.
- Correct the manifest's documentation and issue-tracker links.

## [0.2.2](https://github.com/nelbs/solaredge-forecast/releases/tag/0.2.2) - 2023-10-14

- Fix forecast-period validation in the configuration and options flows,
  including periods spanning calendar years.

## [0.2.1](https://github.com/nelbs/solaredge-forecast/releases/tag/0.2.1) - 2023-07-16

- Correct the remaining-production estimate to subtract today's measured
  production from today's estimate, with a minimum remaining estimate of zero.
- Adjust the progress calculation accordingly.

## [0.2.0](https://github.com/nelbs/solaredge-forecast/releases/tag/0.2.0) - 2023-07-14

- Add a configurable production start date.

## [0.1.5](https://github.com/nelbs/solaredge-forecast/releases/tag/0.1.5) - 2023-07-08

- Limit historical monthly queries to the end of the last completed month.
- Revise the calculation of today's estimate and production progress.

## [0.1.4](https://github.com/nelbs/solaredge-forecast/releases/tag/0.1.4) - 2023-07-07

- Fix the current-month production calculation and revise today's estimate
  and progress handling.
- Include validation workflows and README changes made since 0.1.3.

## [0.1.3](https://github.com/nelbs/solaredge-forecast/releases/tag/0.1.3) - 2023-07-06

- Change the update interval from **60 minutes to 15 minutes**. The original
  release title says "Increase update interval"; the tagged code reduces the
  interval from 3,600 to 900 seconds.

## [0.1.2](https://github.com/nelbs/solaredge-forecast/releases/tag/0.1.2) - 2023-07-05

- Fix a bug in the production-progress sensor.

## [0.1.1](https://github.com/nelbs/solaredge-forecast/releases/tag/0.1.1) - 2023-07-03

- Refine the forecast using interpolated daily production averages.
- Add a sensor comparing production progress with average production.

## [0.1.0](https://github.com/nelbs/solaredge-forecast/releases/tag/0.1.0) - 2023-06-28

- Publish the first version of the SolarEdge Forecast integration.
