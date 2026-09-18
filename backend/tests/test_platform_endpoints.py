from dataclasses import replace

import pytest

from app.ps1.exporter import scenario_csvs
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.scenario_a.policy import prepare
from app.ps1.solver import solve_scenario
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import validate_exported_csvs
from .test_ps1 import DATA
from .test_scenario_a import tiny


@pytest.mark.parametrize("start,end,stations,sectors", [
    ("PLAT:L:S1:EB", "PLAT:L:S3:EB", [1, 2, 3], [1, 2]),
    ("PLAT:L:S1:EB", "SEC:L:S2_S3:EB", [1, 2, 3], [1, 2]),
    ("SEC:L:S1_S2:EB", "PLAT:L:S3:EB", [1, 2, 3], [1, 2]),
    ("PLAT:L:S2:EB", "PLAT:L:S2:EB", [2], []),
    ("PLAT:L:S2:EB", "SEC:L:S1_S2:EB", [1, 2], [1]),
])
def test_platform_work_spans_in_both_orders(start, end, stations, sectors):
    instance = tiny(types=("C",), sectors=4)
    expected = [f"PLAT:L:S{i}:EB" for i in stations]
    expected += [f"SEC:L:S{i}_S{i+1}:EB" for i in sectors]
    for left, right in ((start, end), (end, start)):
        activity = replace(instance.activities["A0"], start_location_id=left, end_location_id=right)
        instance.activities["A0"] = activity
        assert activity_locations(instance, activity) == expected
        assert closure_locations(instance, activity) == set()
        assert prepare(instance).work["A0"] == frozenset(expected)


@pytest.mark.parametrize("nature,radius,mirror", [
    ("Non-live (Others)", 0, False),
    ("Non-live (Consist)", 1, False),
    ("Live", 2, True),
])
@pytest.mark.parametrize("position", [0, 2, 4])
def test_single_platform_buffers_and_line_boundaries(nature, radius, mirror, position):
    instance = tiny(types=("C",), sectors=4)
    instance.contracts["C0"] = replace(instance.contracts["C0"], nature_of_activity=nature)
    location = f"PLAT:L:S{position}:EB"
    activity = replace(instance.activities["A0"], start_location_id=location, end_location_id=location)
    instance.activities["A0"] = activity
    low, high = max(0, position - radius), min(4, position + radius)
    expected = {f"PLAT:L:S{i}:EB" for i in range(low, high + 1)}
    expected |= {f"SEC:L:S{i}_S{i+1}:EB" for i in range(low, high)}
    if mirror:
        expected |= {loc[:-2] + "WB" for loc in expected}
    assert closure_locations(instance, activity) == expected - {location}


def test_parser_accepts_platform_endpoints():
    files = {name: (DATA / name).read_bytes() for name in EXPECTED_FILES}
    files["08_ACTIVITY_DETAILS.csv"] = files["08_ACTIVITY_DETAILS.csv"].replace(
        b"SEC:BET:S15_S16:EB,SEC:BET:S16_S17:EB",
        b"PLAT:BET:S15:EB,PLAT:BET:S17:EB", 1,
    )
    instance = parse_instance(files)
    assert instance.activities["A001"].start_location_id == "PLAT:BET:S15:EB"


@pytest.mark.parametrize("scenario", list(Scenario))
def test_platform_solver_export_and_validation(scenario):
    instance = tiny(types=("C",), sectors=4)
    instance.activities["A0"] = replace(instance.activities["A0"],
        start_location_id="PLAT:L:S1:EB", end_location_id="PLAT:L:S3:EB")
    solution = solve_scenario(instance, scenario, time_limit_seconds=3)
    files = scenario_csvs(solution)
    assert validate_exported_csvs(instance, scenario, files).feasible
    assert {row.location_id for row in solution.occupancy} == {
        "PLAT:L:S1:EB", "PLAT:L:S2:EB", "PLAT:L:S3:EB",
        "SEC:L:S1_S2:EB", "SEC:L:S2_S3:EB",
    }
