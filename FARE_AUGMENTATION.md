# Fare Augmentation

This workspace keeps the downloaded GTFS archives unchanged and generates fare-enriched copies beside them.

## Command

Run the augmenter from the workspace root:

```bash
python3 scripts/augment_gtfs_with_fares.py
```

## Outputs

Generated archives are written to:

- `data-kl/augmented/gtfs_ktmb_fixed_fares.zip`
- `data-kl/augmented/gtfs_erl_fares.zip`
- `data-kl/augmented/gtfs_rapid_rail_kl_fares.zip`
- `data-kl/augmented/gtfs_rapid_bus_kl_fares.zip`
- `data-kl/augmented/gtfs_rapid_bus_mrtfeeder_fares.zip`
- `data-penang/augmented/gtfs_rapid_bus_penang_fares.zip`

Each generated archive keeps the original GTFS files and adds:

- `fare_attributes.txt`
- `fare_rules.txt`

If needed, `stops.txt` is also rewritten in the generated archive to populate `zone_id` values used by the fare rules.

## Current Coverage

- `ktmb`: stop-to-stop matrix from `data-kl/fare/ktmb/fares.csv`
- `erl`: station-to-station fares from `data-kl/fare/erl/fares.csv`
- `rapidrail`: code-based station matrix from `data-kl/fare/rapidrail/fares_cashless.csv`
- `rapidkl`: zonal fares from `data-kl/fare/rapidkl/ride_zones.csv` and `fares_adult.csv`
- `rapidpg`: route-direction stop matrices from `data-penang/fare/rapidpg/fare/*.csv`

Current `rapidpg` coverage improved to most route files, with 10 route files still unmatched after sequence-aware stop matching.

## Known Gaps

- `mrtfb` currently generates an empty fare archive because the fare CSV stop IDs use a different namespace from the static GTFS stop IDs. This is now the main blocker, more than route naming.
- `rapidrail` warns about missing `SA*` station codes because those codes appear in the fare matrix but are not present in the current static GTFS archive.
- `rapidpg` still leaves some fare files unmatched where the matrix does not line up one-to-one with an available GTFS stop sequence. Those need route-specific reconciliation.
- `ktmb` still warns for a few station labels that do not match the trimmed Komuter stop naming exactly.

## Intent

The generated archives are meant to be used for OTP graph builds without mutating the source GTFS downloads.

## Active Runtime Use

The current runtime flow now stages these generated archives into separate build directories:

- `runtime-kl/`
- `runtime-penang/`

That staging is handled by:

```bash
bash scripts/stage_runtime_feeds.sh
```

Current staged feed selection:

- KL uses fare-enriched `ktmb`, `erl`, `rapidrail`, and `rapidkl`
- KL keeps the original `mrtfeeder` GTFS active because its fare CSV stop IDs still do not match the static GTFS stop IDs
- Penang uses the fare-enriched `rapidpg` archive

The standard rebuild flow:

```bash
./scripts/rebuild_and_redeploy_otp.sh
```

regenerates fare archives, stages them into `runtime-*`, rebuilds the graphs from those runtime directories, and restarts both OTP services.