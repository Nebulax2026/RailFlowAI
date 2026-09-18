"""Reproduce unresolved safety semantics without changing inputs or schedules."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ps1.models import OccupancyAssignment, Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.semantics_audit import direct_night_contradictions
from app.ps1.validator import OUTPUT_HEADERS, validate_exported_csvs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "PS1/01_data")
    parser.add_argument("--schedule", type=Path, default=ROOT / "PS1/03_submission_sample")
    parser.add_argument("--scenario", choices=[s.value for s in Scenario], default="A")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inputs = {n: (args.data / n).read_bytes() for n in EXPECTED_FILES}
    files = {n: (args.schedule / n).read_bytes() for n in OUTPUT_HEADERS}
    instance = parse_instance(inputs)
    validation = validate_exported_csvs(instance, Scenario(args.scenario), files)
    rows = csv.DictReader(io.StringIO(files["SCHEDULE_OCCUPANCY.csv"].decode("utf-8-sig")))
    occupancy = [OccupancyAssignment(r["activity_id"], int(r["week"]), r["location_id"], r["co_share_group"]) for r in rows]
    contradictions = direct_night_contradictions(occupancy)
    payload = {
        "purpose": "Interpretation audit, not an official safety verdict.",
        "hypothesis": "Each activity/week occupies its whole span on one physical night; same local groups mean the same night and different local groups mean different nights.",
        "input_sha256": {n: hashlib.sha256(v).hexdigest() for n, v in sorted({**inputs, **files}.items())},
        "current_policy": validation.detail.get("safety_policy"),
        "current_hard_violations": validation.hard_violations,
        "direct_clock_contradiction_count": len(contradictions),
        "direct_clock_contradictions": contradictions,
        "conclusion": "The proposed single-night interpretation is inconsistent with this schedule." if contradictions else "No direct pair contradiction found; this does not prove global consistency or physical safety.",
    }
    content = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"Hard violations: {len(validation.hard_violations)}; direct clock contradictions: {len(contradictions)}; report: {args.output}")
    else:
        print(content)


if __name__ == "__main__":
    main()
