# OpenTripPlanner Deployment Guide

This repository runs two separate OpenTripPlanner 2.9.0 instances:

- Lembah Klang on port `8081`
- Penang on port `8082`

Use this guide on the server after pushing this repository to git and pulling the latest changes.

## What This Repo Deploys

The current deployment model is:

- one staged runtime graph for `runtime-kl`
- one staged runtime graph for `runtime-penang`
- one `docker compose` stack running both services
- optional fare augmentation artifacts generated under `augmented/`

Important:

- source GTFS downloads stay in `data-kl/` and `data-penang/`
- the fare augmenter does not overwrite those source GTFS files
- generated fare-enriched zip files are written under `data-kl/augmented/` and `data-penang/augmented/`
- the rebuild flow stages fare-enabled runtime inputs into `runtime-kl/` and `runtime-penang/`
- OTP now builds and serves from those `runtime-*` directories
- KL still stages the original MRT feeder static feed because its fare CSV namespace does not match the GTFS stop IDs yet

## Repository Layout

```text
otp/
├── data-kl/
│   ├── lembah-klang.osm.pbf
│   ├── router-config.json
│   ├── gtfs_ktmb_fixed.zip
│   ├── gtfs_rapid_rail_kl.zip
│   ├── gtfs_rapid_bus_kl.zip
│   ├── gtfs_rapid_bus_mrtfeeder.zip
│   ├── gtfs_erl.zip
│   ├── graph.obj
│   ├── augmented/
│   ├── archive/
│   ├── disabled-feeds/
│   └── fare/
├── data-penang/
│   ├── penang.osm.pbf
│   ├── router-config.json
│   ├── gtfs_rapid_bus_penang.zip
│   ├── graph.obj
│   ├── augmented/
│   └── fare/
├── runtime-kl/
│   ├── graph.obj
│   ├── lembah-klang.osm.pbf
│   ├── router-config.json
│   └── gtfs_*.zip
├── runtime-penang/
│   ├── graph.obj
│   ├── penang.osm.pbf
│   ├── router-config.json
│   └── gtfs_*.zip
├── docker-compose.yml
├── scripts/
│   ├── augment_gtfs_with_fares.py
│   ├── rebuild_and_redeploy_otp.sh
│   ├── stage_runtime_feeds.sh
│   └── trim_ktmb_kl_komuter.py
├── TWO_AREA_SETUP.md
├── ROUTER_CONFIG_RECOMMENDATIONS.md
└── FARE_AUGMENTATION.md
```

## Server Prerequisites

Install these once on the server:

- Docker Engine with the Compose plugin
- Git
- Python 3

Minimum practical checks:

```bash
docker --version
docker compose version
git --version
python3 --version
```

This repo has been validated with:

- `opentripplanner/opentripplanner:2.9.0`
- `docker compose`
- `python3`

## First-Time Server Setup

Choose a deployment directory, for example:

```bash
mkdir -p /home/deploy/otp
cd /home/deploy/otp
git clone <your-repo-url> .
```

Verify the expected files exist:

```bash
ls data-kl
ls data-penang
ls scripts
```

Make the redeploy script executable once:

```bash
chmod +x scripts/rebuild_and_redeploy_otp.sh
```

## Canonical Deploy Command

After you push changes from your local machine, the standard server workflow is:

```bash
cd /home/deploy/otp
git pull
./scripts/rebuild_and_redeploy_otp.sh
```

That command sequence does all of the following:

1. verifies Docker is available
2. regenerates fare augmentation outputs
3. stages fare-enabled runtime inputs into `runtime-kl/` and `runtime-penang/`
4. stops the currently running OTP containers
5. rebuilds `runtime-kl/graph.obj`
6. rebuilds `runtime-penang/graph.obj`
7. starts both OTP services with `docker compose up -d`

This is the recommended server-side command to redeploy graph, GTFS, OSM, router-config, and script changes in one pass.

## Faster Deploy When Inputs Did Not Change

If you only changed documentation or other repo files that do not affect runtime:

```bash
cd /home/deploy/otp
git pull
```

If you changed only `docker-compose.yml` or runtime configuration and do not need a graph rebuild:

```bash
cd /home/deploy/otp
git pull
docker compose up -d
```

If you want to skip fare augmentation regeneration during a rebuild:

```bash
cd /home/deploy/otp
git pull
./scripts/rebuild_and_redeploy_otp.sh --skip-augment
```

Use `--skip-augment` only when you know the fare CSV inputs and augmentation script have not changed.

## When You Must Rebuild

Run the full rebuild script whenever any of these change:

- any `.osm.pbf` file in `data-kl/` or `data-penang/`
- any top-level GTFS zip used by OTP
- `router-config.json`
- OTP image version in `docker-compose.yml` or the rebuild script
- fare CSV inputs when you want fresh augmented archives
- scripts that prepare or normalize build inputs

Examples:

- you replaced `data-kl/gtfs_rapid_bus_kl.zip`
- you replaced `data-kl/gtfs_rapid_bus_mrtfeeder.zip`
- you replaced `data-penang/gtfs_rapid_bus_penang.zip`
- you updated `data-kl/router-config.json`
- you trimmed KTMB again and replaced `data-kl/gtfs_ktmb_fixed.zip`

## What Was Validated Locally

The current server workflow is based on a locally validated run of:

```bash
./scripts/rebuild_and_redeploy_otp.sh
```

Validated results from that run:

- `runtime-kl/graph.obj` was rebuilt successfully
- `runtime-penang/graph.obj` was rebuilt successfully
- `otp_lembah_klang` restarted on `8081`
- `otp_penang` restarted on `8082`
- both GraphQL endpoints answered route queries after restart
- `ticketTypes` is now populated on both areas
- sample itinerary queries returned real fares, including `MYR 5.2` for a KL rail leg and `MYR 1.4` for a Penang bus leg

## Manual Build Commands

Use these only if you need to debug the process step by step.

### Rebuild Lembah Klang Only

```bash
cd /home/deploy/otp
bash scripts/stage_runtime_feeds.sh
docker rm -f otp_lembah_klang
docker run --rm \
  -e JAVA_TOOL_OPTIONS='-Xmx12G' \
  -v "$PWD/runtime-kl":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --build --save
docker compose up -d otp_lembah_klang
```

### Rebuild Penang Only

```bash
cd /home/deploy/otp
bash scripts/stage_runtime_feeds.sh
docker rm -f otp_penang
docker run --rm \
  -e JAVA_TOOL_OPTIONS='-Xmx8G' \
  -v "$PWD/runtime-penang":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --build --save
docker compose up -d otp_penang
```

### Restart Without Rebuild

```bash
cd /home/deploy/otp
docker compose up -d
```

## Runtime Services

The stack is defined in `docker-compose.yml`:

- `otp_lembah_klang` -> `localhost:8081`
- `otp_penang` -> `localhost:8082`

Current heap settings:

- KL: `-Xmx12G`
- Penang: `-Xmx8G`

If graph builds fail due to memory pressure on the server, increase those values consistently in both the script and `docker-compose.yml`.

## Health Checks After Deploy

### Check Containers

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Expected result:

- `otp_lembah_klang` is `Up`
- `otp_penang` is `Up`

### Check Logs

```bash
docker logs --tail 80 otp_lembah_klang
docker logs --tail 80 otp_penang
```

Look for:

```text
OTP 2.9.0 is ready for routing!
```

### Check GraphQL

Lembah Klang:

```bash
curl -s -X POST http://localhost:8081/otp/gtfs/v1 \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ routes { shortName } }"}'
```

Penang:

```bash
curl -s -X POST http://localhost:8082/otp/gtfs/v1 \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ routes { shortName } }"}'
```

Both should return JSON with route data.

### Check Debug UI

- `http://<server>:8081/`
- `http://<server>:8082/`

## Realtime Notes

Current runtime behavior depends on the router configs already committed in this repo.

Validated feed scope mapping:

- KL: `1=ktmb`, `2=mrtfeeder`, `3=rapid-bus-kl`, `4=erl`, `5=rapidrail`
- Penang: `1=rapid-bus-penang`

The router configs use those numeric `feedId` values because they matched the runtime graphs during testing.

Important:

- this is a working OTP runtime workaround
- it depends on how OTP imported the current static feeds
- if upstream GTFS metadata changes enough, you may need to validate these mappings again

Useful checks:

```bash
docker logs --tail 120 otp_lembah_klang | grep -E 'feedId=1|feedId=2|feedId=3|TRIP_NOT_FOUND|applied successfully|Feed did not contain any updates'
docker logs --tail 120 otp_penang | grep -E 'feedId=1|TRIP_NOT_FOUND|applied successfully|Feed did not contain any updates'
```

## GTFS Refresh Workflow

When you replace static GTFS archives on the server:

1. copy or download the new zip into the correct data directory
2. keep the filename consistent with what the repo expects
3. run the full rebuild script
4. run the GraphQL and log checks

Examples of top-level files currently used by OTP:

- `runtime-kl/gtfs_ktmb_fixed.zip` from `data-kl/augmented/gtfs_ktmb_fixed_fares.zip`
- `runtime-kl/gtfs_rapid_rail_kl.zip` from `data-kl/augmented/gtfs_rapid_rail_kl_fares.zip`
- `runtime-kl/gtfs_rapid_bus_kl.zip` from `data-kl/augmented/gtfs_rapid_bus_kl_fares.zip`
- `runtime-kl/gtfs_rapid_bus_mrtfeeder.zip` from `data-kl/gtfs_rapid_bus_mrtfeeder.zip`
- `runtime-kl/gtfs_erl.zip` from `data-kl/augmented/gtfs_erl_fares.zip`
- `runtime-penang/gtfs_rapid_bus_penang.zip` from `data-penang/augmented/gtfs_rapid_bus_penang_fares.zip`

## Fare Augmentation Workflow

Fare augmentation is non-destructive.

Run manually if you only want to inspect the derived fare outputs:

```bash
cd /home/deploy/otp
python3 scripts/augment_gtfs_with_fares.py
```

Outputs are written under:

- `data-kl/augmented/`
- `data-penang/augmented/`

Known limitations in the current repo state:

- `mrtfb` fare output is effectively empty because fare CSV stop IDs do not match GTFS stop IDs
- `rapidpg` still has a small set of unmatched route files
- `rapidrail` still warns about some fare matrix station codes missing from the GTFS archive

At the moment, those artifacts are no longer just for inspection. The rebuild script stages them into `runtime-kl/` and `runtime-penang/`, and the live OTP graphs are built from those staged runtime directories.

## Reverse Proxy Options

You can expose the two services either by subdomain or by path.

### Recommended: Separate Subdomains

- `kl.example.com` -> `127.0.0.1:8081`
- `penang.example.com` -> `127.0.0.1:8082`

Example Nginx server block for KL:

```nginx
server {
    server_name kl.example.com;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Mirror the same pattern for Penang with port `8082`.

### Alternative: One Domain, Two Paths

- `/kl/` -> `127.0.0.1:8081`
- `/penang/` -> `127.0.0.1:8082`

Use this only if your frontend and API callers are prepared for path-based routing.

## Troubleshooting

### Container Fails to Start

```bash
docker logs otp_lembah_klang
docker logs otp_penang
```

### Graph Version Mismatch

Symptom:

```text
The graph file is incompatible with this version of OTP.
```

Cause:

- `graph.obj` was built with a different OTP version

Fix:

- rebuild with `opentripplanner/opentripplanner:2.9.0`
- keep the image version aligned in both `docker-compose.yml` and `scripts/rebuild_and_redeploy_otp.sh`

### Port Already In Use

```bash
lsof -iTCP:8081 -sTCP:LISTEN
lsof -iTCP:8082 -sTCP:LISTEN
```

Fix either the conflicting process or the host port mapping in `docker-compose.yml`.

### Docker Compose Changed Nothing

If a container with the same name was started outside compose earlier, the rebuild script already removes it first with:

```bash
docker rm -f otp_lembah_klang otp_penang
```

That prevents stale standalone containers from masking compose updates.

### GTFS Build Failure

If the build fails after replacing a feed:

1. identify the broken GTFS archive from the build logs
2. move it out of the active data directory
3. place it under `archive/` or `disabled-feeds/`
4. rebuild again

Example:

```bash
mv data-kl/gtfs_problem.zip data-kl/disabled-feeds/
./scripts/rebuild_and_redeploy_otp.sh --skip-augment
```

### Realtime Vehicles Stop Matching

Likely causes:

- upstream static GTFS changed trip IDs
- OTP imported feeds under different numeric scopes
- upstream realtime payload changed

First checks:

```bash
docker logs --tail 200 otp_lembah_klang
docker logs --tail 200 otp_penang
```

Then re-validate the feed-scope assumptions in `router-config.json`.

## Rollback Strategy

If a fresh deploy is bad:

1. check out the last known-good git revision
2. restore the previous GTFS or OSM inputs if they changed
3. rerun the rebuild script

Example:

```bash
cd /home/deploy/otp
git log --oneline -n 5
git checkout <known-good-commit>
./scripts/rebuild_and_redeploy_otp.sh
```

If you want a safer rollback path, keep dated copies of:

- `data-kl/graph.obj`
- `data-penang/graph.obj`
- replaced GTFS zips

## Recommended Server Prompt

If you later want to prompt from the server with a single instruction, this is the correct operational intent:

```text
cd /home/deploy/otp, git pull, run ./scripts/rebuild_and_redeploy_otp.sh, then verify both OTP containers are up and both GraphQL endpoints return route data.
```

That matches the workflow validated in this repository.
