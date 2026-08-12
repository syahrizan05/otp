#!/usr/bin/env python3

import argparse
import csv
import io
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CURRENCY = "MYR"
DEFAULT_PAYMENT_METHOD = "0"
DEFAULT_TRANSFERS = "0"

KTMB_NAME_ALIASES = {
    "K KUBU BHARU": "KUALA KUBU BARU",
    "KG RAJA UDA": "KAMPUNG RAJA UDA",
    "KG DATO HARUN": "KG DATUK HARUN",
    "KG BATU": "KAMPUNG BATU",
    "JLN.TEMPLER": "JALAN TEMPLER",
    "JLN TEMPLER": "JALAN TEMPLER",
    "PEL. KLANG": "PEL KLANG S",
    "PULAU SEBANG": "PULAU SEBANG TAMPIN",
    "BTG MELAKA": "BATANG MELAKA",
    "SUNGAI BULOH": "SUNGAI BULUH",
    "BANDAR TASEK SELATAN": "BANDAR TASEK S",
    "SEPUTEH": "SEPUTIH",
}

PENANG_NAME_ALIASES = {
    "JETTY B": "TERMINAL B WELD QUAY",
    "BALAI POLIS": "BALAI POLIS LEBUH PANTAI",
    "SWETTENHAM PIER CRUISE TERMINAL": "CHURCH STREET PIER",
    "HOTEL HOLIDAY INN": "PARKROYAL PENANG RESORT",
    "GOLDEN SANDS": "HOTEL GOLDEN SANDS",
    "APARTMEN SRI SAYANG": "SRI SAYANG",
    "LONG BEACH FOOD COURT": "LONG BEACH",
    "PEJABAT POS TG BUNGAH": "PEJABAT POS TGBUNGAH",
    "TESCO TUNKU KUDIN": "LOTUSS SGDUA",
}


@dataclass(frozen=True)
class FareRule:
    fare_id: str
    route_id: str
    origin_id: str
    destination_id: str


def normalize_text(value: str) -> str:
    value = (value or "").strip().upper()
    value = value.replace("&", " AND ")
    value = value.replace("/", " ")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^A-Z0-9 ]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def read_csv_from_zip(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as src:
        text = io.TextIOWrapper(src, encoding="utf-8-sig", newline="")
        rows = list(csv.DictReader(text))
        headers = list(rows[0].keys()) if rows else []
        return headers, rows


def write_csv_to_zip(archive: zipfile.ZipFile, name: str, headers, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(headers), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    archive.writestr(name, buffer.getvalue())


def read_csv_file(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def ensure_column(headers, rows, column_name, default=""):
    if column_name not in headers:
        headers = list(headers) + [column_name]
    for row in rows:
        row.setdefault(column_name, default)
    return headers, rows


def build_stop_lookup(stops):
    lookup = {}
    for row in stops:
        lookup[normalize_text(row["stop_name"])] = row
    return lookup


def copy_zip_with_replacements(source: Path, output: Path, replacements):
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as src_zip, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as out_zip:
        replaced = set(replacements)
        for info in src_zip.infolist():
            if info.filename in replaced:
                continue
            out_zip.writestr(info, src_zip.read(info.filename))

        for name, payload in replacements.items():
            headers, rows = payload
            write_csv_to_zip(out_zip, name, headers, rows)


def create_fare_attribute(fare_id: str, price: str, agency_id: str):
    return {
        "fare_id": fare_id,
        "price": price,
        "currency_type": DEFAULT_CURRENCY,
        "payment_method": DEFAULT_PAYMENT_METHOD,
        "transfers": DEFAULT_TRANSFERS,
        "agency_id": agency_id,
        "transfer_duration": "",
    }


def build_fare_tables(rules_to_price, agency_id):
    fare_attributes = []
    fare_rules = []
    for rule, price in sorted(
        rules_to_price.items(),
        key=lambda item: (item[0].route_id, item[0].origin_id, item[0].destination_id, item[0].fare_id),
    ):
        fare_attributes.append(create_fare_attribute(rule.fare_id, price, agency_id))
        fare_rules.append(
            {
                "fare_id": rule.fare_id,
                "route_id": rule.route_id,
                "origin_id": rule.origin_id,
                "destination_id": rule.destination_id,
                "contains_id": "",
            }
        )

    fare_attribute_headers = [
        "fare_id",
        "price",
        "currency_type",
        "payment_method",
        "transfers",
        "agency_id",
        "transfer_duration",
    ]
    fare_rule_headers = [
        "fare_id",
        "route_id",
        "origin_id",
        "destination_id",
        "contains_id",
    ]
    return (fare_attribute_headers, fare_attributes), (fare_rule_headers, fare_rules)


def set_zone_ids(headers, stops, stop_ids):
    headers, stops = ensure_column(headers, stops, "zone_id", "")
    for row in stops:
        if row["stop_id"] in stop_ids:
            row["zone_id"] = row["stop_id"]
    return headers, stops


def parse_matrix_label(label: str) -> str:
    label = (label or "").strip()
    label = re.sub(r"^\(\d+\)", "", label).strip()
    return re.sub(r"\s+", " ", label).strip()


def canonical_penang_name(value: str) -> str:
    normalized = normalize_text(parse_matrix_label(value))
    return normalize_text(PENANG_NAME_ALIASES.get(normalized, normalized))


def route_short_name_from_matrix_file(path: Path) -> str:
    match = re.match(r"^([A-Za-z0-9]+)", path.stem)
    return match.group(1) if match else path.stem.split("-", 1)[0].strip()


def normalize_header_map(row):
    return {
        normalize_text(key).replace(" ", "_").lower(): value
        for key, value in row.items()
    }


def canonical_zone_label(value: str) -> str:
    cleaned = normalize_text(value)
    if cleaned.isdigit():
        return f"Zone {cleaned}"
    if cleaned.startswith("ZONE "):
        return f"Zone {cleaned.split()[-1]}"
    return value.strip()


def build_trip_sequences(source: Path):
    with zipfile.ZipFile(source) as src_zip:
        _, stops = read_csv_from_zip(src_zip, "stops.txt")
        _, trips = read_csv_from_zip(src_zip, "trips.txt")
        _, stop_times = read_csv_from_zip(src_zip, "stop_times.txt")

    stop_by_id = {row["stop_id"]: row for row in stops}
    trip_meta = {row["trip_id"]: row for row in trips}
    trip_times = defaultdict(list)
    for row in stop_times:
        if row["trip_id"] not in trip_meta:
            continue
        trip_times[row["trip_id"]].append((int(row["stop_sequence"]), row["stop_id"]))

    unique_sequences = defaultdict(list)
    for trip_id, pairs in trip_times.items():
        ordered = [stop_id for _, stop_id in sorted(pairs)]
        route_id = trip_meta[trip_id]["route_id"]
        signature = tuple(ordered)
        unique_sequences[route_id].append(
            {
                "trip_id": trip_id,
                "direction_id": trip_meta[trip_id].get("direction_id", ""),
                "headsign": trip_meta[trip_id].get("trip_headsign", ""),
                "stop_ids": ordered,
                "stop_names": [stop_by_id[stop_id]["stop_name"] for stop_id in ordered],
                "signature": signature,
            }
        )

    deduped = {}
    for route_id, items in unique_sequences.items():
        seen = set()
        route_sequences = []
        for item in items:
            key = item["signature"]
            if key in seen:
                continue
            seen.add(key)
            route_sequences.append(item)
        deduped[route_id] = route_sequences
    return deduped


def best_sequence_for_labels(route_sequences, labels):
    target = [normalize_text(parse_matrix_label(label)) for label in labels]
    candidates = [item for item in route_sequences if len(item["stop_ids"]) == len(target)]
    if not candidates:
        return None

    def score(item):
        names = [normalize_text(name) for name in item["stop_names"]]
        exact = sum(1 for left, right in zip(names, target) if left == right)
        endpoints = int(names[0] == target[0]) + int(names[-1] == target[-1])
        return (exact, endpoints)

    return max(candidates, key=score)


def names_match(label_name: str, stop_name: str) -> bool:
    left = canonical_penang_name(label_name)
    right = canonical_penang_name(stop_name)
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    return len(left_tokens & right_tokens) >= 2


def align_labels_to_sequence(labels, sequence_names):
    mapping = {}
    label_index = 0
    sequence_index = 0
    while label_index < len(labels) and sequence_index < len(sequence_names):
        if names_match(labels[label_index], sequence_names[sequence_index]):
            mapping[label_index] = sequence_index
            label_index += 1
            sequence_index += 1
            continue

        found = False
        for lookahead in range(sequence_index + 1, min(len(sequence_names), sequence_index + 5)):
            if names_match(labels[label_index], sequence_names[lookahead]):
                mapping[label_index] = lookahead
                label_index += 1
                sequence_index = lookahead + 1
                found = True
                break
        if found:
            continue

        for lookahead in range(label_index + 1, min(len(labels), label_index + 5)):
            if names_match(labels[lookahead], sequence_names[sequence_index]):
                label_index = lookahead
                found = True
                break
        if not found:
            label_index += 1

    return mapping


def best_ordered_sequence_for_labels(route_sequences, labels):
    best = None
    best_mapping = None
    best_score = (-1, -1, -1)
    for sequence in route_sequences:
        mapping = align_labels_to_sequence(labels, sequence["stop_names"])
        if not mapping:
            continue
        matched = len(mapping)
        endpoints = int(0 in mapping) + int((len(labels) - 1) in mapping)
        score = (matched, endpoints, -abs(len(sequence["stop_names"]) - len(labels)))
        if score > best_score:
            best = sequence
            best_mapping = mapping
            best_score = score
    return best, best_mapping, best_score


def augment_station_matrix_feed(source: Path, output: Path, matrix_path: Path, agency_id: str, fare_prefix: str, price_columns):
    with zipfile.ZipFile(source) as src_zip:
        stop_headers, stops = read_csv_from_zip(src_zip, "stops.txt")

    stop_lookup = build_stop_lookup(stops)
    rows = read_csv_rows(matrix_path)
    destination_labels = rows[0][2:]

    stop_ids = set()
    rules_to_price = {}
    unresolved = set()

    for raw_row in rows[1:]:
        origin_label = raw_row[0].strip()
        origin_lookup_key = KTMB_NAME_ALIASES.get(normalize_text(origin_label), origin_label)
        origin_stop = stop_lookup.get(normalize_text(origin_lookup_key))
        if not origin_stop:
            unresolved.add(origin_label)
            continue

        for offset, destination_label in enumerate(destination_labels, start=2):
            if offset >= len(raw_row):
                continue
            destination_lookup_key = KTMB_NAME_ALIASES.get(
                normalize_text(destination_label), destination_label
            )
            destination_stop = stop_lookup.get(normalize_text(destination_lookup_key))
            if not destination_stop:
                unresolved.add(destination_label)
                continue

            stop_ids.add(origin_stop["stop_id"])
            stop_ids.add(destination_stop["stop_id"])

            for product_name, column_index in price_columns.items():
                price = raw_row[column_index] if column_index < len(raw_row) else ""
                price = price.strip()
                if not price or price == "-":
                    continue
                fare_id = (
                    f"{fare_prefix}:{product_name}:{origin_stop['stop_id']}:{destination_stop['stop_id']}"
                )
                rule = FareRule(
                    fare_id=fare_id,
                    route_id="",
                    origin_id=origin_stop["stop_id"],
                    destination_id=destination_stop["stop_id"],
                )
                rules_to_price[rule] = price

    if unresolved:
        print(
            f"warning: {source.name} skipped {len(unresolved)} unresolved station labels: {sorted(unresolved)[:8]}",
            file=sys.stderr,
        )

    stop_headers, stops = set_zone_ids(stop_headers, stops, stop_ids)
    fare_attributes, fare_rules = build_fare_tables(rules_to_price, agency_id)
    replacements = {
        "stops.txt": (stop_headers, stops),
        "fare_attributes.txt": fare_attributes,
        "fare_rules.txt": fare_rules,
    }
    copy_zip_with_replacements(source, output, replacements)
    return len(rules_to_price), len(stop_ids)


def augment_code_matrix_feed(source: Path, output: Path, matrix_path: Path, agency_id: str, fare_prefix: str, price_columns):
    with zipfile.ZipFile(source) as src_zip:
        stop_headers, stops = read_csv_from_zip(src_zip, "stops.txt")

    stop_by_id = {row["stop_id"]: row for row in stops}
    rows = read_csv_rows(matrix_path)
    destination_codes = [cell.strip() for cell in rows[0][2:]]

    stop_ids = set()
    rules_to_price = {}
    unresolved = set()

    for raw_row in rows[1:]:
        origin_code = raw_row[0].strip()
        origin_stop = stop_by_id.get(origin_code)
        if not origin_stop:
            unresolved.add(origin_code)
            continue

        for offset, destination_code in enumerate(destination_codes, start=2):
            if offset >= len(raw_row):
                continue
            destination_stop = stop_by_id.get(destination_code)
            if not destination_stop:
                unresolved.add(destination_code)
                continue

            stop_ids.add(origin_stop["stop_id"])
            stop_ids.add(destination_stop["stop_id"])

            for product_name, column_index in price_columns.items():
                price = raw_row[column_index] if column_index < len(raw_row) else ""
                price = price.strip()
                if not price or price == "-":
                    continue
                fare_id = (
                    f"{fare_prefix}:{product_name}:{origin_stop['stop_id']}:{destination_stop['stop_id']}"
                )
                rule = FareRule(
                    fare_id=fare_id,
                    route_id="",
                    origin_id=origin_stop["stop_id"],
                    destination_id=destination_stop["stop_id"],
                )
                rules_to_price[rule] = price

    if unresolved:
        print(
            f"warning: {source.name} skipped {len(unresolved)} unresolved station codes: {sorted(unresolved)[:8]}",
            file=sys.stderr,
        )

    stop_headers, stops = set_zone_ids(stop_headers, stops, stop_ids)
    fare_attributes, fare_rules = build_fare_tables(rules_to_price, agency_id)
    replacements = {
        "stops.txt": (stop_headers, stops),
        "fare_attributes.txt": fare_attributes,
        "fare_rules.txt": fare_rules,
    }
    copy_zip_with_replacements(source, output, replacements)
    return len(rules_to_price), len(stop_ids)


def augment_erl_feed(source: Path, output: Path, matrix_path: Path):
    with zipfile.ZipFile(source) as src_zip:
        stop_headers, stops = read_csv_from_zip(src_zip, "stops.txt")

    stop_lookup = build_stop_lookup(stops)
    stop_ids = set()
    rules_to_price = {}
    rows = read_csv_file(matrix_path)
    for row in rows:
        origin = stop_lookup.get(normalize_text(row["from"]))
        destination = stop_lookup.get(normalize_text(row["to"]))
        if not origin or not destination:
            continue
        stop_ids.add(origin["stop_id"])
        stop_ids.add(destination["stop_id"])
        for product_name in ("cash", "cashless", "concession"):
            price = row[product_name].strip()
            if not price:
                continue
            fare_id = f"erl:{product_name}:{origin['stop_id']}:{destination['stop_id']}"
            rule = FareRule(
                fare_id=fare_id,
                route_id="",
                origin_id=origin["stop_id"],
                destination_id=destination["stop_id"],
            )
            rules_to_price[rule] = price

    stop_headers, stops = set_zone_ids(stop_headers, stops, stop_ids)
    fare_attributes, fare_rules = build_fare_tables(rules_to_price, "erl")
    replacements = {
        "stops.txt": (stop_headers, stops),
        "fare_attributes.txt": fare_attributes,
        "fare_rules.txt": fare_rules,
    }
    copy_zip_with_replacements(source, output, replacements)
    return len(rules_to_price), len(stop_ids)


def augment_rapidpg_feed(source: Path, output: Path, fare_dir: Path):
    with zipfile.ZipFile(source) as src_zip:
        stop_headers, stops = read_csv_from_zip(src_zip, "stops.txt")
        _, routes = read_csv_from_zip(src_zip, "routes.txt")

    route_by_short_name = {row["route_short_name"]: row["route_id"] for row in routes}
    sequences_by_route = build_trip_sequences(source)

    stop_ids = set()
    rules_to_price = {}
    unmatched_files = []

    for matrix_path in sorted(fare_dir.glob("*.csv")):
        route_short_name = route_short_name_from_matrix_file(matrix_path)
        route_id = route_by_short_name.get(route_short_name)
        if not route_id:
            unmatched_files.append(matrix_path.name)
            continue

        rows = read_csv_rows(matrix_path)
        labels = rows[0][1:]
        sequence, mapping, score = best_ordered_sequence_for_labels(
            sequences_by_route.get(route_id, []), labels
        )
        if not sequence or not mapping or score[0] < max(6, int(len(sequence["stop_ids"]) * 0.6)):
            unmatched_files.append(matrix_path.name)
            continue

        for stop_id in sequence["stop_ids"]:
            stop_ids.add(stop_id)

        for origin_index, raw_row in enumerate(rows[1:]):
            if origin_index not in mapping:
                continue
            origin_stop_id = sequence["stop_ids"][mapping[origin_index]]
            for destination_index, price in enumerate(raw_row[1:]):
                price = price.strip()
                if not price or destination_index not in mapping:
                    continue
                destination_stop_id = sequence["stop_ids"][mapping[destination_index]]
                fare_id = f"rapidpg:adult:{route_id}:{origin_stop_id}:{destination_stop_id}"
                rule = FareRule(
                    fare_id=fare_id,
                    route_id=route_id,
                    origin_id=origin_stop_id,
                    destination_id=destination_stop_id,
                )
                rules_to_price[rule] = price

    if unmatched_files:
        print(
            f"warning: {source.name} could not map {len(unmatched_files)} fare files: {', '.join(unmatched_files[:8])}",
            file=sys.stderr,
        )

    stop_headers, stops = set_zone_ids(stop_headers, stops, stop_ids)
    fare_attributes, fare_rules = build_fare_tables(rules_to_price, "rapidpg")
    replacements = {
        "stops.txt": (stop_headers, stops),
        "fare_attributes.txt": fare_attributes,
        "fare_rules.txt": fare_rules,
    }
    copy_zip_with_replacements(source, output, replacements)
    return len(rules_to_price), len(stop_ids), len(unmatched_files)


def augment_zonal_feed(source: Path, output: Path, fare_dir: Path, agency_id: str):
    with zipfile.ZipFile(source) as src_zip:
        stop_headers, stops = read_csv_from_zip(src_zip, "stops.txt")
        _, routes = read_csv_from_zip(src_zip, "routes.txt")

    route_lookup = {row["route_id"]: row for row in routes}
    route_lookup_by_name = {}
    for row in routes:
        if row.get("route_short_name"):
            route_lookup_by_name[row["route_short_name"].strip()] = row["route_id"]
        if row.get("route_long_name"):
            route_lookup_by_name[row["route_long_name"].strip()] = row["route_id"]
    stop_by_id = {row["stop_id"]: row for row in stops}

    fare_types = read_csv_file(fare_dir / "fare_types.csv")
    ride_zones = read_csv_file(fare_dir / "ride_zones.csv")
    fares_adult = read_csv_file(fare_dir / "fares_adult.csv")
    fares_concession_path = fare_dir / "fares_concession.csv"
    fares_concession = read_csv_file(fares_concession_path) if fares_concession_path.exists() else []

    zone_prices = {}
    for row in fares_adult:
        normalized_row = normalize_header_map(row)
        from_zone = normalized_row["ride_zone"].strip()
        for column, price in normalized_row.items():
            if column == "ride_zone" or not price.strip():
                continue
            zone_prices[("adult", canonical_zone_label(from_zone), canonical_zone_label(column))] = price.strip()

    for row in fares_concession:
        normalized_row = normalize_header_map(row)
        from_zone = normalized_row["ride_zone"].strip()
        for column, price in normalized_row.items():
            if column == "ride_zone" or not price.strip():
                continue
            zone_prices[("concession", canonical_zone_label(from_zone), canonical_zone_label(column))] = price.strip()

    line_to_route = {}
    for row in fare_types:
        route_id = row["route_id"].strip()
        if route_id in route_lookup:
            line_to_route[row["CBTS LINE_ID"].strip()] = route_id
            continue
        actual_route = row.get("Actual Route", "").strip()
        mapped_route_id = route_lookup_by_name.get(actual_route)
        if mapped_route_id:
            line_to_route[row["CBTS LINE_ID"].strip()] = mapped_route_id

    line_zone_rows = defaultdict(list)
    for row in ride_zones:
        normalized_row = normalize_header_map(row)
        line_zone_rows[normalized_row["line_id"].strip()].append(normalized_row)

    rules_to_price = {}
    stop_ids = set()
    unresolved_lines = []
    for line_id, zone_rows in line_zone_rows.items():
        route_id = line_to_route.get(line_id)
        if not route_id:
            unresolved_lines.append(line_id)
            continue

        ordered_rows = sorted(zone_rows, key=lambda row: int(row["order"]))
        for row in ordered_rows:
            stop_id = row.get("stop_id", "").strip()
            if stop_id in stop_by_id:
                stop_ids.add(stop_id)

        for origin in ordered_rows:
            origin_stop_id = origin.get("stop_id", "").strip()
            if origin_stop_id not in stop_by_id:
                continue
            for destination in ordered_rows:
                destination_stop_id = destination.get("stop_id", "").strip()
                if destination_stop_id not in stop_by_id:
                    continue
                for product_name in ("adult", "concession"):
                    price = zone_prices.get(
                        (
                            product_name,
                            canonical_zone_label(origin.get("ride_zone", "")),
                            canonical_zone_label(destination.get("alight_zone", "")),
                        )
                    )
                    if not price:
                        continue
                    fare_id = (
                        f"{agency_id}:{product_name}:{route_id}:{origin_stop_id}:{destination_stop_id}"
                    )
                    rule = FareRule(
                        fare_id=fare_id,
                        route_id=route_id,
                        origin_id=origin_stop_id,
                        destination_id=destination_stop_id,
                    )
                    rules_to_price[rule] = price

    if unresolved_lines:
        print(
            f"warning: {source.name} skipped {len(unresolved_lines)} unmapped lines: {', '.join(sorted(unresolved_lines)[:8])}",
            file=sys.stderr,
        )

    stop_headers, stops = set_zone_ids(stop_headers, stops, stop_ids)
    fare_attributes, fare_rules = build_fare_tables(rules_to_price, agency_id)
    replacements = {
        "stops.txt": (stop_headers, stops),
        "fare_attributes.txt": fare_attributes,
        "fare_rules.txt": fare_rules,
    }
    copy_zip_with_replacements(source, output, replacements)
    return len(rules_to_price), len(stop_ids), len(unresolved_lines)


def run_all(workspace_root: Path):
    results = []
    results.append(
        (
            "ktmb",
            augment_station_matrix_feed(
                workspace_root / "data-kl" / "gtfs_ktmb_fixed.zip",
                workspace_root / "data-kl" / "augmented" / "gtfs_ktmb_fixed_fares.zip",
                workspace_root / "data-kl" / "fare" / "ktmb" / "fares.csv",
                "ktmb",
                "ktmb",
                {"adult": 2},
            ),
        )
    )
    results.append(
        (
            "erl",
            augment_erl_feed(
                workspace_root / "data-kl" / "gtfs_erl.zip",
                workspace_root / "data-kl" / "augmented" / "gtfs_erl_fares.zip",
                workspace_root / "data-kl" / "fare" / "erl" / "fares.csv",
            ),
        )
    )
    results.append(
        (
            "rapidrail",
            augment_code_matrix_feed(
                workspace_root / "data-kl" / "gtfs_rapid_rail_kl.zip",
                workspace_root / "data-kl" / "augmented" / "gtfs_rapid_rail_kl_fares.zip",
                workspace_root / "data-kl" / "fare" / "rapidrail" / "fares_cashless.csv",
                "rapidrail",
                "rapidrail",
                {"cashless": 2},
            ),
        )
    )
    results.append(
        (
            "rapidkl",
            augment_zonal_feed(
                workspace_root / "data-kl" / "gtfs_rapid_bus_kl.zip",
                workspace_root / "data-kl" / "augmented" / "gtfs_rapid_bus_kl_fares.zip",
                workspace_root / "data-kl" / "fare" / "rapidkl",
                "rapidkl",
            ),
        )
    )
    results.append(
        (
            "mrtfb",
            augment_zonal_feed(
                workspace_root / "data-kl" / "gtfs_rapid_bus_mrtfeeder.zip",
                workspace_root / "data-kl" / "augmented" / "gtfs_rapid_bus_mrtfeeder_fares.zip",
                workspace_root / "data-kl" / "fare" / "mrtfb",
                "mrtfb",
            ),
        )
    )
    results.append(
        (
            "rapidpg",
            augment_rapidpg_feed(
                workspace_root / "data-penang" / "gtfs_rapid_bus_penang.zip",
                workspace_root / "data-penang" / "augmented" / "gtfs_rapid_bus_penang_fares.zip",
                workspace_root / "data-penang" / "fare" / "rapidpg" / "fare",
            ),
        )
    )
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate fare-enriched GTFS archives beside the original source zips."
    )
    parser.add_argument(
        "workspace_root",
        nargs="?",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Workspace root containing data-kl and data-penang",
    )
    args = parser.parse_args()

    results = run_all(args.workspace_root)
    for name, payload in results:
        print(f"{name}: {payload}")


if __name__ == "__main__":
    main()