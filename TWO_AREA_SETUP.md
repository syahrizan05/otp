# Two-Area OTP Setup

This layout runs two separate OTP instances:

- `otp_lembah_klang` on port `8081`
- `otp_penang` on port `8082`

Use this pattern when journeys are only planned within each area. If you need a
single itinerary from Lembah Klang to Penang, build one combined graph instead.

## Recommended Layout

```text
otp/
├── data-kl/
│   ├── lembah-klang.osm.pbf
│   ├── gtfs_*.zip
│   └── router-config.json
├── data-penang/
│   ├── penang.osm.pbf
│   ├── gtfs_*.zip
│   └── router-config.json
├── runtime-kl/
│   ├── graph.obj
│   ├── lembah-klang.osm.pbf
│   ├── gtfs_*.zip
│   └── router-config.json
├── runtime-penang/
│   ├── graph.obj
│   ├── penang.osm.pbf
│   ├── gtfs_*.zip
│   └── router-config.json
├── docker-compose.yml
├── scripts/stage_runtime_feeds.sh
└── TWO_AREA_SETUP.md
```

## What Stays Separate

Each area should have its own:

- OSM extract
- source GTFS files
- staged runtime GTFS files
- `graph.obj`
- `router-config.json`
- realtime updater configuration

Do not place both area OSM files in the same data directory when using this two-instance design.

Current runtime behavior in this repo:

- `data-kl/` and `data-penang/` keep the original downloads and fare CSV inputs
- `runtime-kl/` and `runtime-penang/` are generated staging directories used for OTP build and serve
- `docker-compose.yml` mounts `runtime-kl/` and `runtime-penang/`
- `scripts/stage_runtime_feeds.sh` refreshes those runtime directories without mutating the source GTFS downloads

## Build Each Graph

### Lembah Klang

```bash
cd /Users/syahrizan.ali/projects/otp
bash scripts/stage_runtime_feeds.sh

docker run --rm \
  -e JAVA_TOOL_OPTIONS='-Xmx12G' \
  -v "$PWD/runtime-kl":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --build --save
```

### Penang

```bash
cd /Users/syahrizan.ali/projects/otp
bash scripts/stage_runtime_feeds.sh

docker run --rm \
  -e JAVA_TOOL_OPTIONS='-Xmx8G' \
  -v "$PWD/runtime-penang":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --build --save
```

Adjust heap upward if the Penang graph is larger than expected.

## Static GTFS Sources

Official GTFS static endpoints used in this repo:

- Lembah Klang bus: `https://api.data.gov.my/gtfs-static/prasarana?category=rapid-bus-kl`
- Lembah Klang MRT feeder: `https://api.data.gov.my/gtfs-static/prasarana?category=rapid-bus-mrtfeeder`
- Lembah Klang rail: `https://api.data.gov.my/gtfs-static/prasarana?category=rapid-rail-kl`
- KTMB: `https://api.data.gov.my/gtfs-static/ktmb`
- Penang bus: `https://api.data.gov.my/gtfs-static/prasarana?category=rapid-bus-penang`

Refresh them with `curl -L ... -o <file>.zip`, then rebuild the corresponding graph.

For fare-enabled builds, do not replace the runtime files directly. Refresh the source archive under `data-kl/` or `data-penang/`, rerun the fare augmenter if needed, then rerun `bash scripts/stage_runtime_feeds.sh` or `./scripts/rebuild_and_redeploy_otp.sh`.

## Realtime Sources

Official GTFS realtime vehicle position endpoints used in router configs:

- Lembah Klang bus: `https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-kl`
- Lembah Klang MRT feeder: `https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-mrtfeeder`
- KTMB: `https://api.data.gov.my/gtfs-realtime/vehicle-position/ktmb`
- Penang bus: `https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-penang`

Notes:

- Realtime vehicle feeds update every `30s`.
- `rapid-rail-kl` does not currently have a stable realtime feed.
- `rapid-bus-penang` has known static/realtime trip ID mismatches from the provider, so realtime may need custom trip ID matching later.
- OTP may import static GTFS feeds under internal numeric feed scopes rather than the human updater labels.

Verified runtime scopes in this repo:

- KL: `1=ktmb`, `2=mrtfeeder`, `3=rapid-bus-kl`, `4=erl`, `5=rapidrail`
- Penang: `1=rapid-bus-penang`

Current router configs use those numeric scopes because they were validated against the running graphs.

Important: this is a working runtime workaround, not the ideal permanent fix. The better long-term fix is to clean up or normalize the GTFS metadata so OTP imports stable feed identifiers without needing numeric scope patching.

## Start Both Services

```bash
cd /Users/syahrizan.ali/projects/otp
bash scripts/stage_runtime_feeds.sh
docker compose up -d
```

## Stop Both Services

```bash
cd /Users/syahrizan.ali/projects/otp
docker compose down
```

## Verify Each Area

### Lembah Klang

```bash
curl -s -X POST http://localhost:8081/otp/gtfs/v1 \
  -H 'Content-Type: application/json' \
  -d '{"query":"{routes{shortName}}"}'
```

### Penang

```bash
curl -s -X POST http://localhost:8082/otp/gtfs/v1 \
  -H 'Content-Type: application/json' \
  -d '{"query":"{routes{shortName}}"}'
```

## Verify Realtime Matching

After changing `router-config.json`, restart the affected container and inspect logs.

KL:

```bash
docker restart otp_lembah_klang
docker logs --tail 120 otp_lembah_klang | grep -E '\\[feedId=1|\\[feedId=2|\\[feedId=3|applied successfully|TRIP_NOT_FOUND|Feed did not contain any updates'
```

Penang:

```bash
docker restart otp_penang
docker logs --tail 120 otp_penang | grep -E '\\[feedId=1|applied successfully|TRIP_NOT_FOUND|Feed did not contain any updates'
```

Known validated result from this repo state:

- KL MRT feeder: `109 of 111` updates applied successfully
- Penang: `120 of 149` updates applied successfully

## Frontend Routing Pattern

Use one of these approaches:

1. Let the user select the service area, then call the matching OTP base URL.
2. Infer the area from origin and destination coordinates, then route to the matching OTP instance.

Do not send a request spanning both areas to one of these isolated instances and expect a valid intercity itinerary.

## Reverse Proxy Pattern

If you expose both through one domain, map them to separate paths or subdomains:

- `/kl/*` -> `http://127.0.0.1:8081/*`
- `/penang/*` -> `http://127.0.0.1:8082/*`

or:

- `kl.example.com` -> `http://127.0.0.1:8081`
- `penang.example.com` -> `http://127.0.0.1:8082`

## When To Change Strategy

Switch to one combined graph if you later need:

- Lembah Klang to Penang trip planning in one query
- intercity rail or bus itineraries across both areas
- one unified nationwide API instead of area-specific endpoints