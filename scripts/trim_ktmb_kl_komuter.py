#!/usr/bin/env python3

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path


KEEP_ROUTE_IDS = {"KA15_KD19", "KC05_KB18"}


def read_csv_from_zip(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as src:
        text = io.TextIOWrapper(src, encoding="utf-8-sig", newline="")
        rows = list(csv.DictReader(text))
        headers = rows[0].keys() if rows else []
        return list(headers), rows


def write_csv_to_zip(archive: zipfile.ZipFile, name: str, headers, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(headers), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    archive.writestr(name, buffer.getvalue())


def main():
    parser = argparse.ArgumentParser(
        description="Trim KTMB GTFS to Klang Valley Komuter routes only."
    )
    parser.add_argument("source", type=Path, help="Source KTMB GTFS zip")
    parser.add_argument("output", type=Path, help="Output trimmed GTFS zip")
    args = parser.parse_args()

    with zipfile.ZipFile(args.source) as src_zip:
        route_headers, routes = read_csv_from_zip(src_zip, "routes.txt")
        trip_headers, trips = read_csv_from_zip(src_zip, "trips.txt")
        stop_time_headers, stop_times = read_csv_from_zip(src_zip, "stop_times.txt")
        stop_headers, stops = read_csv_from_zip(src_zip, "stops.txt")
        calendar_headers, calendar = read_csv_from_zip(src_zip, "calendar.txt")
        agency_headers, agencies = read_csv_from_zip(src_zip, "agency.txt")

    kept_routes = [row for row in routes if row["route_id"] in KEEP_ROUTE_IDS]
    kept_route_ids = {row["route_id"] for row in kept_routes}

    kept_trips = [row for row in trips if row["route_id"] in kept_route_ids]
    kept_trip_ids = {row["trip_id"] for row in kept_trips}
    kept_service_ids = {row["service_id"] for row in kept_trips}

    kept_stop_times = [row for row in stop_times if row["trip_id"] in kept_trip_ids]
    kept_stop_ids = {row["stop_id"] for row in kept_stop_times}

    kept_stops = [row for row in stops if row["stop_id"] in kept_stop_ids]
    kept_calendar = [row for row in calendar if row["service_id"] in kept_service_ids]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
        write_csv_to_zip(out_zip, "agency.txt", agency_headers, agencies)
        write_csv_to_zip(out_zip, "calendar.txt", calendar_headers, kept_calendar)
        write_csv_to_zip(out_zip, "routes.txt", route_headers, kept_routes)
        write_csv_to_zip(out_zip, "trips.txt", trip_headers, kept_trips)
        write_csv_to_zip(out_zip, "stop_times.txt", stop_time_headers, kept_stop_times)
        write_csv_to_zip(out_zip, "stops.txt", stop_headers, kept_stops)

    print(
        f"Wrote {args.output} with {len(kept_routes)} routes, "
        f"{len(kept_trips)} trips, {len(kept_stop_times)} stop_times, and {len(kept_stops)} stops.",
        file=sys.stdout,
    )


if __name__ == "__main__":
    main()