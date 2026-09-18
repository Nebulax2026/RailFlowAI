from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from ortools.sat.python import cp_model

from app.ps1.models import AccessAssignment, ContractResult, Instance, OccupancyAssignment, Scenario, ScenarioSolution
from app.ps1.topology import activity_locations, closure_locations
from app.ps1.validator import validate_solution

PRIORITY_WEIGHTS = {1: 1000, 2: 100, 3: 10}
ACTIVITY_NUDGES = {1: 13, 2: 12, 3: 10}


def solve_scenario(instance: Instance, scenario: Scenario, time_limit_seconds: float = 30.0) -> ScenarioSolution:
    model = cp_model.CpModel()
    assignments: dict[tuple[str, int, int, int], cp_model.BoolVar] = {}
    activity_weeks: dict[tuple[str, int], cp_model.IntVar] = {}
    activity_access_counts: dict[str, int] = {}
    activity_eclo_counts: dict[str, int] = {}
    location_terms: dict[tuple[str, int], list[tuple[cp_model.BoolVar, str]]] = defaultdict(list)
    contract_night_terms: dict[tuple[str, int, int], list[cp_model.BoolVar]] = defaultdict(list)

    for activity in instance.activities.values():
        contract = instance.contracts[activity.contract_number]
        earliest = _week_for_date(instance, activity.planned_start_date)
        latest = instance.horizon_weeks
        if scenario == Scenario.B:
            latest = min(latest, _week_for_date(instance, contract.planned_completion_date))
        available_weeks = latest - earliest + 1
        access_count = activity.total_accesses
        if scenario == Scenario.B and available_weeks < activity.total_accesses:
            minimum_rows = math.ceil(activity.total_accesses / 1.5)
            if available_weeks < minimum_rows:
                raise ValueError(f"{scenario}: {activity.activity_id} cannot fit even with ECLO before its limit.")
            access_count = available_weeks
        activity_access_counts[activity.activity_id] = access_count
        activity_eclo_counts[activity.activity_id] = 2 * (activity.total_accesses - access_count)

        locations = activity_locations(instance, activity)
        reserved_locations = closure_locations(instance, activity)
        for access_index in range(access_count):
            week_var = model.NewIntVar(earliest, latest, f"week_{activity.activity_id}_{access_index}")
            activity_weeks[(activity.activity_id, access_index)] = week_var
            if access_index:
                model.Add(activity_weeks[(activity.activity_id, access_index - 1)] < week_var)
            choices = []
            for week in range(earliest, latest + 1):
                for night in range(1, contract.number_of_maximum_access_per_week + 1):
                    selected = model.NewBoolVar(f"x_{activity.activity_id}_{access_index}_{week}_{night}")
                    assignments[(activity.activity_id, access_index, week, night)] = selected
                    choices.append(selected)
                    model.Add(week_var == week).OnlyEnforceIf(selected)
                    contract_night_terms[(activity.contract_number, week, night)].append(selected)
                    for location in locations:
                        location_terms[(location, week)].append((selected, contract.access_type))
                    for location in reserved_locations:
                        location_terms[(location, week)].append((selected, "BUFFER"))
            model.AddExactlyOne(choices)

    for activity in instance.activities.values():
        if activity.predecessor_activity_id:
            predecessor = instance.activities[activity.predecessor_activity_id]
            model.Add(
                activity_weeks[(predecessor.activity_id, activity_access_counts[predecessor.activity_id] - 1)]
                < activity_weeks[(activity.activity_id, 0)]
            )

    for (contract_number, _week, _night), terms in contract_night_terms.items():
        contract = instance.contracts[contract_number]
        model.Add(sum(terms) <= contract.number_of_workfronts)

    excess_vars = []
    for (location, week), typed_terms in location_terms.items():
        supply = instance.supply[location].supply_capacity
        terms = [term for term, _access_type in typed_terms]
        # One possession can hold one PC plus three C activities, or four C.
        # PM consumes a whole possession by itself. This weighted relaxation is
        # paired with deterministic legal grouping in the exported occupancy.
        weighted_usage = sum(term * (4 if access_type in {"PM", "BUFFER"} else 1) for term, access_type in typed_terms)
        possession_starters = sum(term for term, access_type in typed_terms if access_type in {"PM", "PC", "BUFFER"})
        if scenario == Scenario.A:
            model.Add(weighted_usage <= supply * 4)
            model.Add(possession_starters <= supply)
        elif scenario == Scenario.C:
            model.Add(weighted_usage <= (supply + 1) * 4)
            model.Add(possession_starters <= supply + 1)
        if scenario in {Scenario.B, Scenario.C}:
            estimated_possessions = model.NewIntVar(0, len(terms), f"possessions_{_safe(location)}_{week}")
            model.Add(estimated_possessions * 4 >= weighted_usage)
            model.Add(estimated_possessions >= possession_starters)
            excess = model.NewIntVar(0, max(0, len(terms) - supply), f"excess_{_safe(location)}_{week}")
            model.Add(excess >= estimated_possessions - supply)
            excess_vars.append(excess)

    completion_vars = {}
    objective_terms = []
    for contract in instance.contracts.values():
        activity_ids = [item.activity_id for item in instance.activities.values() if item.contract_number == contract.contract_number]
        last_weeks = [activity_weeks[(item_id, activity_access_counts[item_id] - 1)] for item_id in activity_ids]
        completion = model.NewIntVar(1, instance.horizon_weeks, f"completion_{contract.contract_number}")
        model.AddMaxEquality(completion, last_weeks)
        completion_vars[contract.contract_number] = completion
        planned_week = _week_for_date(instance, contract.planned_completion_date)
        if scenario == Scenario.B:
            model.Add(completion <= planned_week)
        else:
            overrun = model.NewIntVar(0, instance.horizon_weeks, f"overrun_{contract.contract_number}")
            model.Add(overrun >= completion - planned_week)
            objective_terms.append(overrun * PRIORITY_WEIGHTS[contract.contract_priority] * 7)

    if excess_vars:
        objective_terms.append(sum(excess_vars) * 7)
    # Stable tie-breaker: earlier aggregate access placement.
    objective_terms.append(sum(activity_weeks.values()))
    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError(f"No complete {scenario} schedule found within the configured horizon.")

    accesses: list[AccessAssignment] = []
    occupancy_members: dict[tuple[str, int], list[str]] = defaultdict(list)
    for activity in sorted(instance.activities.values(), key=lambda item: item.activity_id):
        locations = activity_locations(instance, activity)
        for index in range(activity_access_counts[activity.activity_id]):
            chosen_week = solver.Value(activity_weeks[(activity.activity_id, index)])
            contract = instance.contracts[activity.contract_number]
            chosen_night = next(
                night for night in range(1, contract.number_of_maximum_access_per_week + 1)
                if solver.Value(assignments[(activity.activity_id, index, chosen_week, night)])
            )
            eclo = int(index < activity_eclo_counts[activity.activity_id])
            accesses.append(AccessAssignment(activity.activity_id, index + 1, chosen_week, eclo, chosen_night))
            for location in locations:
                occupancy_members[(location, chosen_week)].append(activity.activity_id)

    occupancy = _pack_occupancy(instance, occupancy_members)

    results = []
    for contract in sorted(instance.contracts.values(), key=lambda item: item.contract_number):
        completion_week = solver.Value(completion_vars[contract.contract_number])
        completion_date = instance.horizon_start + timedelta(days=completion_week * 7 - 1)
        results.append(
            ContractResult(
                scenario.value,
                contract.contract_number,
                completion_date,
                max(0, (completion_date - contract.planned_completion_date).days),
            )
        )

    validation = validate_solution(instance, scenario, accesses, occupancy, results)
    explanations = _explanations(instance, scenario, results, validation.soft_scores)
    return ScenarioSolution(scenario, accesses, occupancy, results, validation, explanations)


def _week_for_date(instance: Instance, value) -> int:
    return max(1, min(instance.horizon_weeks, math.floor((value - instance.horizon_start).days / 7) + 1))


def _safe(value: str) -> str:
    return value.replace(":", "_").replace("-", "_")


def _pack_occupancy(instance: Instance, members: dict[tuple[str, int], list[str]]) -> list[OccupancyAssignment]:
    output: list[OccupancyAssignment] = []
    for (location, week), activity_ids in sorted(members.items()):
        unique_ids = sorted(set(activity_ids))
        pms = [item for item in unique_ids if instance.contracts[instance.activities[item].contract_number].access_type == "PM"]
        pcs = [item for item in unique_ids if instance.contracts[instance.activities[item].contract_number].access_type == "PC"]
        coworkers = [item for item in unique_ids if instance.contracts[instance.activities[item].contract_number].access_type == "C"]
        groups: list[list[str]] = [[item] for item in pms]
        for pc in pcs:
            group = [pc, *coworkers[:3]]
            coworkers = coworkers[3:]
            groups.append(group)
        while coworkers:
            groups.append(coworkers[:4])
            coworkers = coworkers[4:]
        for index, group in enumerate(groups, start=1):
            label = f"g{week}-{index}"
            output.extend(OccupancyAssignment(activity_id, week, location, label) for activity_id in group)
    return sorted(output, key=lambda item: (item.activity_id, item.week, item.location_id))


def _explanations(instance: Instance, scenario: Scenario, results: list[ContractResult], scores: dict) -> list[str]:
    delayed = sorted((item for item in results if item.overrun_days), key=lambda item: item.overrun_days, reverse=True)
    messages = [f"Scenario {scenario.value} schedules all {sum(a.total_accesses for a in instance.activities.values())} access units."]
    if delayed:
        messages.append(f"{len(delayed)} contracts finish after their planned date; {delayed[0].contract_number} has the largest overrun.")
    else:
        messages.append("All contracts finish on or before their planned completion date.")
    if scores.get("excess_access_nights_total", 0):
        messages.append(f"Flexible supply adds {scores['excess_access_nights_total']} location-week access slots.")
    return messages
