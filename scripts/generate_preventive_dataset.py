"""Reproducibly create the experimental preventive-maintenance public dataset."""
from __future__ import annotations

import csv
import shutil
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "PS1" / "01_data"
TARGET = ROOT / "PS1" / "01_data_preventive"
TRADEOFF_TARGET = ROOT / "PS1" / "01_data_preventive_tradeoff"
WEEKDAYS = ("FRI", "SAT", "SUN")
DEMO_CONTRACT = (
    "C015", "Preventive maintenance trade-off demonstration", "2026-01-01", "Renewal",
    "Non-live (Others)", 1, "2027-08-01", "2027-01-10", 1, "C", 5,
)
DEMO_LOCATIONS = (
    "SEC:ALP:S01_S02:EB",
    "SEC:ALP:S03_S04:EB",
    "SEC:ALP:S05_S06:EB",
    "SEC:ALP:S07_S08:EB",
    "SEC:BET:S11_S12:EB",
)


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for source in sorted(SOURCE.glob("*.csv")):
        shutil.copyfile(source, TARGET / source.name)
    with (SOURCE / "06_PARAMETERS.csv").open(newline="", encoding="utf-8") as stream:
        parameters = {row["key"]: row["value"] for row in csv.DictReader(stream)}
    horizon_start = date.fromisoformat(parameters["horizon_start"])
    horizon_end = horizon_start + timedelta(days=int(parameters["horizon_weeks"]) * 7 - 1)
    with (SOURCE / "04_LOCATION_SUPPLY.csv").open(newline="", encoding="utf-8") as stream:
        locations = sorted(row["location_id"] for row in csv.DictReader(stream))
    headers = ("rule_id", "location_id", "weekday", "start_time", "end_time",
               "recurrence_start_date", "recurrence_end_date", "max_deferral_days")
    with (TARGET / "09_PREVENTIVE_MAINTENANCE.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(headers)
        for location_index, location in enumerate(locations, 1):
            for weekday in WEEKDAYS:
                writer.writerow((f"PM-{location_index:03d}-{weekday}", location, weekday, "01:00", "04:00",
                                 horizon_start.isoformat(), horizon_end.isoformat(), 7))
    if TRADEOFF_TARGET.exists():
        shutil.rmtree(TRADEOFF_TARGET)
    shutil.copytree(TARGET, TRADEOFF_TARGET)
    with (TRADEOFF_TARGET / "07_PROJECT_DETAILS.csv").open("a", newline="", encoding="utf-8") as stream:
        csv.writer(stream, lineterminator="\n").writerow(DEMO_CONTRACT)
    with (TRADEOFF_TARGET / "08_ACTIVITY_DETAILS.csv").open("a", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        for index, location in enumerate(DEMO_LOCATIONS, 1):
            writer.writerow((f"PMD{index:02d}", "C015", "Renewal", location, location, 1,
                             horizon_start.isoformat(), "", 1))


if __name__ == "__main__":
    main()
