from __future__ import annotations

from app.ps1.models import Activity, Instance, Sector


def _activity_span(instance: Instance, activity: Activity) -> tuple[list[Sector], list[str], int, int]:
    """Map SEC intervals and PLAT points to inclusive station boundaries."""
    start = instance.supply[activity.start_location_id]
    end = instance.supply[activity.end_location_id]
    if start.line_code != end.line_code or start.bound != end.bound:
        raise ValueError(f"{activity.activity_id}: activity endpoints must share a line and bound.")
    sectors = sorted(
        (sector for sector in instance.sectors.values() if sector.line_code == start.line_code),
        key=lambda item: item.seq,
    )
    station_ids = [station.station_id for station in sorted(
        (station for station in instance.stations.values() if station.line_code == start.line_code),
        key=lambda station: station.seq,
    )]
    positions = {f"PLAT:{start.line_code}:{station}:{start.bound}": (i, i)
                 for i, station in enumerate(station_ids)}
    positions.update({f"{sector.sector_id}:{start.bound}": (i, i + 1)
                      for i, sector in enumerate(sectors)})
    if activity.start_location_id not in positions or activity.end_location_id not in positions:
        raise ValueError(f"{activity.activity_id}: endpoint is not present in topology.")
    left, right = positions[activity.start_location_id], positions[activity.end_location_id]
    return sectors, station_ids, min(left[0], right[0]), max(left[1], right[1])


def activity_locations(instance: Instance, activity: Activity) -> list[str]:
    sectors, station_ids, low, high = _activity_span(instance, activity)
    start = instance.supply[activity.start_location_id]
    bound = start.bound
    locations = [f"PLAT:{start.line_code}:{station_id}:{bound}" for station_id in station_ids[low:high + 1]]
    locations.extend(f"{sector.sector_id}:{bound}" for sector in sectors[low:high])
    missing = [location for location in locations if location not in instance.supply]
    if missing:
        raise ValueError(f"{activity.activity_id}: expanded locations missing from supply: {', '.join(missing)}")
    return locations


def affected_lines(instance: Instance, activity: Activity) -> set[str]:
    contract = instance.contracts[activity.contract_number]
    line = instance.supply[activity.start_location_id].line_code
    if contract.nature_of_activity == "Live" and any("H01_H02" in value for value in activity_locations(instance, activity)):
        return set(instance.lines)
    return {line}


def closure_locations(instance: Instance, activity: Activity) -> set[str]:
    """Locations reserved by buffers/mirroring in addition to reported occupancy."""
    actual = set(activity_locations(instance, activity))
    contract = instance.contracts[activity.contract_number]
    rule = instance.buffer_rules[contract.nature_of_activity]
    start_supply = instance.supply[activity.start_location_id]
    line = start_supply.line_code
    bound = start_supply.bound
    sectors, station_ids, low, high = _activity_span(instance, activity)
    left = max(0, low - rule.up_to_buffer_sectors)
    right = min(len(sectors), high + rule.up_to_buffer_sectors)
    buffered = {
        f"{sector.sector_id}:{bound}"
        for sector in sectors[left:right]
    }
    if rule.up_to_buffer_sectors:
        buffered.update(f"PLAT:{line}:{station}:{bound}" for station in station_ids[left:right + 1])
    reserved = actual | buffered
    if rule.opposite_bound_required:
        other_bound = "WB" if bound == "EB" else "EB"
        reserved |= {location.rsplit(":", 1)[0] + f":{other_bound}" for location in reserved}
    if contract.nature_of_activity == "Live" and any("H01_H02" in location for location in actual):
        other_lines = set(instance.lines) - {line}
        for other_line in other_lines:
            for affected_bound in {"EB", "WB"}:
                reserved.update(
                    {
                        f"SEC:{other_line}:H01_H02:{affected_bound}",
                        f"PLAT:{other_line}:H01:{affected_bound}",
                        f"PLAT:{other_line}:H02:{affected_bound}",
                    }
                )
    return {location for location in reserved if location in instance.supply} - actual


def protection_details(instance: Instance, activity: Activity) -> dict[str, list[str]]:
    work = set(activity_locations(instance, activity))
    protected = closure_locations(instance, activity)
    source = instance.supply[activity.start_location_id]
    return {
        "work": sorted(work),
        "buffer": sorted(p for p in protected if instance.supply[p].line_code == source.line_code and instance.supply[p].bound == source.bound),
        "opposite_bound": sorted(p for p in protected if instance.supply[p].line_code == source.line_code and instance.supply[p].bound != source.bound),
        "interchange": sorted(p for p in protected if instance.supply[p].line_code != source.line_code),
    }
