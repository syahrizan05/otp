# Penang OTP Data

Place the Penang-specific OTP inputs in this directory:

- `penang.osm.pbf`
- `gtfs_rapid_bus_penang.zip`
- `router-config.json`
- generated `graph.obj`

Current official source URLs:

- Static GTFS: `https://api.data.gov.my/gtfs-static/prasarana?category=rapid-bus-penang`
- Realtime vehicle positions: `https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-penang`

Build the graph with:

```bash
cd /Users/syahrizan.ali/projects/otp/data-penang

docker run --rm \
  -e JAVA_TOOL_OPTIONS='-Xmx8G' \
  -v "$PWD":/var/opentripplanner \
  opentripplanner/opentripplanner:2.9.0 \
  --build --save
```

After `graph.obj` exists, start both areas from the repo root:

```bash
cd /Users/syahrizan.ali/projects/otp
docker compose up -d
```