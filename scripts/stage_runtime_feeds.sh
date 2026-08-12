#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

stage_file() {
  local source_path="$1"
  local target_path="$2"

  ln -f "$source_path" "$target_path"
}

stage_kl() {
  local runtime_dir="$ROOT_DIR/runtime-kl"

  rm -rf "$runtime_dir"
  mkdir -p "$runtime_dir"

  stage_file "$ROOT_DIR/data-kl/lembah-klang.osm.pbf" "$runtime_dir/lembah-klang.osm.pbf"
  stage_file "$ROOT_DIR/data-kl/router-config.json" "$runtime_dir/router-config.json"
  stage_file "$ROOT_DIR/data-kl/augmented/gtfs_ktmb_fixed_fares.zip" "$runtime_dir/gtfs_ktmb_fixed.zip"
  stage_file "$ROOT_DIR/data-kl/augmented/gtfs_erl_fares.zip" "$runtime_dir/gtfs_erl.zip"
  stage_file "$ROOT_DIR/data-kl/augmented/gtfs_rapid_rail_kl_fares.zip" "$runtime_dir/gtfs_rapid_rail_kl.zip"
  stage_file "$ROOT_DIR/data-kl/augmented/gtfs_rapid_bus_kl_fares.zip" "$runtime_dir/gtfs_rapid_bus_kl.zip"
  # MRT feeder fare CSV stop IDs do not match GTFS stop IDs yet, so keep the original feed active.
  stage_file "$ROOT_DIR/data-kl/gtfs_rapid_bus_mrtfeeder.zip" "$runtime_dir/gtfs_rapid_bus_mrtfeeder.zip"
}

stage_penang() {
  local runtime_dir="$ROOT_DIR/runtime-penang"

  rm -rf "$runtime_dir"
  mkdir -p "$runtime_dir"

  stage_file "$ROOT_DIR/data-penang/penang.osm.pbf" "$runtime_dir/penang.osm.pbf"
  stage_file "$ROOT_DIR/data-penang/router-config.json" "$runtime_dir/router-config.json"
  stage_file "$ROOT_DIR/data-penang/augmented/gtfs_rapid_bus_penang_fares.zip" "$runtime_dir/gtfs_rapid_bus_penang.zip"
}

cd "$ROOT_DIR"

stage_kl
stage_penang

echo "Staged fare-enabled runtime inputs:"
echo "- runtime-kl"
echo "- runtime-penang"