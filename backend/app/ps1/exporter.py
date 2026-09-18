from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict

from app.ps1.models import ScenarioSolution


def validation_summary(report):
    """Compact portable report; complete location evidence stays in scenario API."""
    payload = asdict(report)
    detail = payload['detail']
    detail.pop('location_usage', None)
    hotspots = detail.get('capacity_hotspots', [])
    detail['capacity_hotspots_total'] = len(hotspots)
    detail['capacity_hotspots'] = [{k: row[k] for k in ('location_id', 'week', 'used', 'capacity', 'work_possessions', 'protection_possessions') if k in row} for row in hotspots[:100]]
    return payload


def scenario_csvs(solution: ScenarioSolution) -> dict[str, bytes]:
    return {
        "SCHEDULE_ACCESS.csv": _csv_bytes(
            ("activity_id", "access_seq", "week", "eclo", "access_night"),
            ([item.activity_id, item.access_seq, item.week, item.eclo, item.access_night] for item in solution.accesses),
        ),
        "SCHEDULE_OCCUPANCY.csv": _csv_bytes(
            ("activity_id", "week", "location_id", "co_share_group"),
            ([item.activity_id, item.week, item.location_id, item.co_share_group] for item in solution.occupancy),
        ),
        "RESULTS.csv": _csv_bytes(
            ("scenario", "contract_number", "simulated_completion_date", "overrun_days"),
            ([item.scenario, item.contract_number, item.simulated_completion_date.isoformat(), item.overrun_days] for item in solution.results),
        ),
    }


def solutions_zip(solutions: list[ScenarioSolution]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        summary = {}
        for solution in solutions:
            for filename, content in scenario_csvs(solution).items():
                archive.writestr(f"scenario_{solution.scenario.value}/{filename}", content)
            summary[solution.scenario.value] = validation_summary(solution.validation)
        archive.writestr("validation_summary.json", json.dumps(summary, indent=2, default=str))
        archive.writestr("manifest.json", json.dumps({"included_scenarios": [s.scenario.value for s in solutions],
                            "revisions": {s.scenario.value: s.solution_revision for s in solutions}}, indent=2))
    return stream.getvalue()


def _csv_bytes(headers, rows) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")
