# Router Config Recommendations

This note documents the recommended OTP 2.9 runtime configuration for the two-area setup in this repository.

These settings are applied in:

- `data-kl/router-config.json`
- `data-penang/router-config.json`

They are runtime settings, not graph-build inputs. In practice this means:

- changing `router-config.json` does not usually require rebuilding `graph.obj`
- you must restart the OTP container for the affected area to load the new config
- if no router config is found at startup, OTP falls back to the config embedded in the graph

## Design Goals

The recommended configuration tries to balance three things:

1. stable response times
2. useful itineraries without too many low-quality results
3. conservative realtime behavior based on the public Malaysia transport feeds currently available

## Lembah Klang Profile

Lembah Klang is the larger and more complex router:

- more stops and routes
- multiple feed families
- more legitimate transfer-heavy journeys
- more cases where a wider search window is justified

Recommended choices:

- `apiProcessingTimeout: 8s`
- `numItineraries: 8`
- `transferPenalty: 120`
- `accessEgress.maxDuration: 30m`
- `transit.maxNumberOfTransfers: 8`
- `transit.maxSearchWindow: PT2H`

Justification:

- KL journeys can span urban rail, feeder bus, and intercity rail combinations.
- A moderate transfer penalty discourages noisy transfer chains without suppressing valid multimodal journeys.
- A 2-hour maximum search window is wide enough for longer metro-region trips while still limiting expensive searches.

## Penang Profile

Penang is simpler operationally and should stay tighter:

- fewer routes
- mostly bus-oriented routing
- lower value in returning many near-duplicate itineraries

Recommended choices:

- `apiProcessingTimeout: 6s`
- `numItineraries: 6`
- `transferPenalty: 180`
- `accessEgress.maxDuration: 25m`
- `transit.maxNumberOfTransfers: 6`
- `transit.maxSearchWindow: PT90M`

Justification:

- Penang benefits from stronger suppression of low-value bus transfer chains.
- A narrower search window helps latency and keeps results focused on local journeys.

## Shared Runtime Choices

Both routers use:

- `timetableUpdates.maxSnapshotFrequency: 2s`
- `timetableUpdates.purgeExpiredData: true`
- `walk.speed: 1.3`
- `walk.boardCost: 600`
- `dynamicSearchWindow.stepMinutes: 10`

Justification:

- These values are conservative defaults for public transit trip planning.
- They avoid unnecessary churn in timetable snapshots and keep walking preferences within a normal range.

## Realtime Updaters In Use

Current updaters are all `vehicle-positions` updaters.

KL:

- `rapid-bus-kl`
- `rapid-bus-mrtfeeder`
- `ktmb`

Penang:

- `rapid-bus-penang`

All are polled at `30s`, which matches the public provider documentation.

## Verified Feed Scope Behavior

During runtime validation, OTP did not use the human feed labels from the updater config as the imported feed scopes.

Observed runtime scopes in KL:

- `1` = KTMB
- `2` = MRT feeder bus
- `3` = Rapid Bus KL
- `4` = ERL
- `5` = Rapid Rail

Observed runtime scope in Penang:

- `1` = Rapid Penang

Because of that, the working updater configuration in this repo now uses the runtime numeric feed scopes instead of labels like `rapid-bus-mrtfeeder`.

Validated outcomes after restart:

- KL MRT feeder improved from `0%` applied to `109 of 111` applied
- Penang improved from `0%` applied to `120 of 149` applied
- KL `rapid-bus-kl` and `ktmb` still returned empty realtime payloads during sampled polls

## What Vehicle Positions Actually Do

Vehicle position updaters:

- attach live vehicle location data to the loaded graph
- expose vehicle positions through OTP APIs
- support live map and operational use cases

Vehicle positions do not, by themselves, provide fully delay-aware journey planning. For that, OTP needs GTFS-RT trip updates via a `stop-time-updater`.

In practical terms for this repo:

- vehicle positions help OTP attach live vehicle locations to active trips when trip matching succeeds
- this improves operational visibility and any UI or API surface that reads live vehicle data
- routing quality only improves indirectly and only where OTP can associate the live vehicle with the correct scheduled trip
- they do not replace proper static GTFS quality or GTFS-RT trip updates

## Provider-Specific Caveats

### KTMB

The official `gtfs_ktmb.zip` feed was not buildable in OTP 2.9 during testing. A user-provided replacement `gtfs_ktmb_fixed.zip` rebuilt successfully and is the currently working KL rail input.

### Rapid Bus Penang

The public realtime documentation notes known static/realtime trip ID mismatch issues for `rapid-bus-penang`.

Operational implication:

- vehicle positions may still be exposed
- some realtime matches may fail or be incomplete
- this should be treated as best-effort live visibility, not proof of realtime routing quality

### Feed Scope Workaround Versus Real Fix

The current numeric `feedId` values in `router-config.json` are a runtime workaround, not the preferred long-term design.

Why this happened:

- some static GTFS inputs do not provide stable feed metadata such as `feed_info.txt`
- some inputs also omit `agency_id`
- OTP then assigns internal numeric feed scopes during import

Why this is fragile:

- numeric scopes can change if feed import order changes
- the workaround can break after future graph rebuilds if upstream feeds change

The proper fix is to normalize the GTFS inputs so they expose stable identifiers before graph build. In practice that means preferring GTFS that includes stable feed metadata, or patching the GTFS package itself so OTP does not need to invent numeric scopes.

Reminder for future maintenance: do not treat the numeric `feedId` patch as the final solution. Fix the GTFS metadata or upstream feed packaging when possible.

## What We Intentionally Did Not Tune Yet

The following were left conservative on purpose:

- `searchThreadPoolSize`
- custom `transferCacheRequests`
- per-mode transfer cost tuning beyond basic defaults
- advanced itinerary filters
- request tracing and monitoring-specific headers

These should be changed only after observing real traffic, latency, and result quality.

## Operational Notes

After changing either router config:

1. restart the affected OTP container
2. verify the API responds
3. check logs for updater match failures or unexpected timeout behavior

For this repo, examples are:

```bash
docker restart otp_penang
docker restart otp_lembah_klang
```

or, if you are using Compose:

```bash
docker compose up -d
```