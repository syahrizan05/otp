# OpenTripPlanner (OTP) — Lembah Klang Deployment Guide

**Server:** `otp.nscs.site`  
**OTP Version:** 2.9.0 (stable)  
**Date Deployed:** June 15, 2026  
**Co-hosted app:** `pmes.nscs.site` (unaffected, ports 3000/4000)

---

## Directory Structure

```
/home/deploy/otp/lembah_klang_2_9/
├── data/
│   ├── lembah-klang.osm.pbf          # OSM street map for Lembah Klang
│   ├── gtfs_rapid_bus_kl.zip         # Rapid Bus KL schedule
│   ├── gtfs_rapid_bus_mrtfeeder.zip  # Rapid MRT Feeder schedule
│   ├── gtfs_rapid_rail_kl.zip        # Rapid Rail KL schedule
│   ├── graph.obj                     # Built OTP graph (do not edit)
│   ├── router-config.json            # Runtime config (updaters, routing defaults)
│   └── disabled-feeds/
│       └── gtfs_ktmb.zip             # KTMB feed — disabled (bad stop_time data)
└── DEPLOYMENT.md                     # This file
```

---

## Port Allocation

| Service        | Internal Port | Host Port | Public URL             |
|----------------|---------------|-----------|------------------------|
| OTP container  | 8080          | 8081      | https://otp.nscs.site  |
| Next.js (pmes) | 3000          | 3000      | https://pmes.nscs.site |
| Express (pmes) | 4000          | 4000      | https://pmes.nscs.site |

---

## Running OTP

### Start (production)
```bash
cd /home/deploy/otp/lembah_klang_2_9/data
docker run -d --restart unless-stopped --name otp_lembah_klang \
  -p 8081:8080 \
  -v "$PWD":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --load --serve
```

### Stop / Remove
```bash
docker rm -f otp_lembah_klang
```

### View logs
```bash
docker logs -f otp_lembah_klang
```
OTP is ready when logs show:
```
OTP 2.9.0 is ready for routing!
```

### Restart (e.g. after reboot)
The container has `--restart unless-stopped`, so it will auto-start with Docker daemon. To manually restart:
```bash
docker restart otp_lembah_klang
```

---

## Rebuilding the Graph

Rebuild is required when you update any input file (OSM, GTFS) or switch OTP versions.

```bash
cd /home/deploy/otp/lembah_klang_2_9/data

# Stop current server
docker rm -f otp_lembah_klang

# Rebuild graph.obj (takes ~2 mins)
docker run --rm \
  -v "$PWD":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --build --save

# Restart server
docker run -d --restart unless-stopped --name otp_lembah_klang \
  -p 8081:8080 \
  -v "$PWD":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --load --serve
```

> **Important:** Always rebuild with the same OTP image version you use to serve.
> Mixing versions causes a serialization version mismatch error and OTP will refuse to start.

---

## Updating Input Data

### Update a GTFS feed
```bash
cd /home/deploy/otp/lembah_klang_2_9/data
# Replace the zip file, then rebuild graph
wget -O gtfs_rapid_bus_kl.zip <new-url>
# then run rebuild steps above
```

### Update OSM data
```bash
# Download latest Lembah Klang extract from Geofabrik or BBBike
wget -O lembah-klang.osm.pbf <new-url>
# then run rebuild steps above
```

---

## Nginx Configuration

File: `/etc/nginx/sites-available/otp`

```nginx
server {
    server_name otp.nscs.site;

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

    listen 443 ssl; # managed by Certbot
    # ... SSL certs below managed by Certbot
}
```

Reload Nginx after any config change:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## SSL Certificate

Issued by Let's Encrypt via Certbot.

- **Certificate:** `/etc/letsencrypt/live/otp.nscs.site/fullchain.pem`
- **Key:** `/etc/letsencrypt/live/otp.nscs.site/privkey.pem`
- **Expires:** 2026-09-13 (auto-renewed by Certbot timer)

Check renewal status:
```bash
sudo certbot renew --dry-run
```

---

## Cloudflare DNS

| Type | Name  | Value            | Proxy     |
|------|-------|------------------|-----------|
| A    | otp   | 178.105.197.154  | Proxied or DNS-only |

SSL/TLS mode in Cloudflare dashboard should be set to **Full (strict)**.

---

## Real-Time Vehicle Positions

Configured in `data/router-config.json`:

| Feed ID             | Source URL                                                   |
|---------------------|--------------------------------------------------------------|
| rapid-bus-kl        | `api.data.gov.my/.../prasarana?category=rapid-bus-kl`       |
| rapid-bus-mrtfeeder | `api.data.gov.my/.../prasarana?category=rapid-bus-mrtfeeder`|
| ktmb                | `api.data.gov.my/.../ktmb` *(in config but no GTFS loaded)* |

### Testing vehicle positions

**1. Check OTP updater status:**
```bash
curl -s https://otp.nscs.site/otp/updaters | python3 -m json.tool
```

**2. Check raw GTFS-RT feed is alive:**
```bash
curl -s "https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-kl" | wc -c
# Non-zero = feed is responding
```

**3. Decode feed (human-readable):**
```bash
pip install gtfs-realtime-bindings
python3 -c "
from google.transit import gtfs_realtime_pb2
import urllib.request
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(urllib.request.urlopen(
  'https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-kl'
).read())
print(f'{len(feed.entity)} vehicles in feed')
for e in feed.entity[:3]: print(e)
"
```

**4. End-to-end GraphQL query:**
```bash
curl -s -X POST https://otp.nscs.site/otp/gtfs/v1 \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ routes { shortName vehiclePositions { vehicleId label lat lon } } }"}' \
  | python3 -m json.tool | head -80
```

---

## Troubleshooting

### OTP container won't start / exits immediately
Check logs:
```bash
docker logs otp_lembah_klang
```

**Serialization version mismatch:**
```
The graph file is incompatible with this version of OTP.
The OTP serialization version id 'X' do not match the id 'Y'
```
→ The `graph.obj` was built with a different OTP version. Rebuild the graph with the same image you are serving with (see "Rebuilding the Graph" above).

---

**GTFS build crash — NullPointerException on stop_time:**
```
Trip <Trip ktmb_26> contains stop_time with no stop, location or group.
```
→ The GTFS file has corrupt/missing stop references. Move the offending zip out of the data directory:
```bash
mkdir -p data/disabled-feeds
mv data/gtfs_ktmb.zip data/disabled-feeds/
```
Then rebuild the graph.

---

**Port already in use:**
```bash
ss -ltn | grep 8081
```
→ Change the host port mapping (e.g. `-p 8082:8080`) and update the Nginx `proxy_pass` accordingly.

---

**Nginx 502 Bad Gateway:**
OTP is still loading — it takes ~20–30 seconds after container start to be ready. Wait and retry. Check:
```bash
docker logs --tail 20 otp_lembah_klang | grep -E "ready|ERROR|SHUTTING"
```

---

**Vehicle position TRIP_NOT_FOUND errors in logs:**
```
Could not match any vehicle positions for feedId 'ktmb'
```
→ The real-time feed has trip IDs that don't exist in the loaded GTFS. Either the GTFS is stale or the feed ID doesn't match. For KTMB specifically this is expected since `gtfs_ktmb.zip` is disabled. Remove the ktmb updater block from `router-config.json` to silence these warnings (requires container restart, no graph rebuild needed).

---

## Useful API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /otp` | Server info (version, uptime) |
| `GET /otp/updaters` | Real-time updater status |
| `POST /otp/gtfs/v1` | GTFS GraphQL API |
| `POST /otp/transmodel/v3` | Transmodel GraphQL API |
| `GET /otp/debug-ui/` | Built-in debug map UI |

Debug UI (route planner in browser):
```
https://otp.nscs.site/otp/debug-ui/
```
