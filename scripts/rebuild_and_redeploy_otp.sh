#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OTP_IMAGE="opentripplanner/opentripplanner:2.9.0"
RUN_AUGMENT=1

usage() {
  cat <<'EOF'
Usage: scripts/rebuild_and_redeploy_otp.sh [--skip-augment]

Rebuilds the KL and Penang OTP graphs, then restarts the runtime containers.

Options:
  --skip-augment   Skip fare augmentation generation before rebuilding.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-augment)
      RUN_AUGMENT=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

cd "$ROOT_DIR"

echo "[1/7] Checking Docker availability"
docker info >/dev/null
docker compose version >/dev/null

if [[ "$RUN_AUGMENT" -eq 1 ]]; then
  echo "[2/7] Regenerating fare augmentation artifacts"
  python3 scripts/augment_gtfs_with_fares.py
else
  echo "[2/7] Skipping fare augmentation generation"
fi

echo "[3/7] Staging fare-enabled runtime inputs"
bash scripts/stage_runtime_feeds.sh

echo "[4/7] Stopping running OTP containers before graph rebuild"
docker rm -f otp_lembah_klang otp_penang >/dev/null 2>&1 || true

echo "[5/7] Rebuilding Lembah Klang graph"
docker run --rm \
  -e JAVA_TOOL_OPTIONS='-Xmx12G' \
  -v "$ROOT_DIR/runtime-kl":/var/opentripplanner \
  "$OTP_IMAGE" \
  --build --save

echo "[6/7] Rebuilding Penang graph"
docker run --rm \
  -e JAVA_TOOL_OPTIONS='-Xmx8G' \
  -v "$ROOT_DIR/runtime-penang":/var/opentripplanner \
  "$OTP_IMAGE" \
  --build --save

echo "[7/7] Starting OTP services with docker compose"
docker compose up -d

echo
echo "OTP redeploy complete."
echo "- KL:     http://localhost:8081/"
echo "- Penang: http://localhost:8082/"
echo
echo "Quick verification commands:"
echo "  docker logs --tail 80 otp_lembah_klang"
echo "  docker logs --tail 80 otp_penang"
echo "  curl -s -X POST http://localhost:8081/otp/gtfs/v1 -H 'Content-Type: application/json' -d '{\"query\":\"{ routes { shortName } }\"}' | head"
echo "  curl -s -X POST http://localhost:8082/otp/gtfs/v1 -H 'Content-Type: application/json' -d '{\"query\":\"{ routes { shortName } }\"}' | head"