from __future__ import annotations

from app.ps1.models import Activity, Instance


def activity_locations(instance: Instance, activity: Activity) -> list[str]:
    start = instance.supply[activity.start_location_id]
    end = instance.supply[activity.end_location_id]
    if start.line_code != end.line_code or start.bound != end.bound:
        raise ValueError(f"{activity.activity_id}: activity endpoints must share a line and bound.")
    if not activity.start_location_id.startswith("SEC:") or not activity.end_location_id.startswith("SEC:"):
        raise ValueError(f"{activity.activity_id}: this PS1 implementation expects SEC endpoints.")

    sectors = sorted(
        (sector for sector in instance.sectors.values() if sector.line_code == start.line_code),
        key=lambda item: item.seq,
    )
    by_base = {sector.sector_id: sector for sector in sectors}
    start_base = activity.start_location_id.rsplit(":", 1)[0]
    end_base = activity.end_location_id.rsplit(":", 1)[0]
    if start_base not in by_base or end_base not in by_base:
        raise ValueError(f"{activity.activity_id}: sector endpoint is not present in 03_SECTORS.csv.")
    low, high = sorted((by_base[start_base].seq, by_base[end_base].seq))
    span = [sector for sector in sectors if low <= sector.seq <= high]
    station_ids = [span[0].from_station_id, *[sector.to_station_id for sector in span]]
    bound = start.bound
    locations = [f"PLAT:{start.line_code}:{station_id}:{bound}" for station_id in station_ids]
    locations.extend(f"{sector.sector_id}:{bound}" for sector in span)
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
    sectors = sorted((item for item in instance.sectors.values() if item.line_code == line), key=lambda item: item.seq)
    by_id = {item.sector_id: item for item in sectors}
    start_sector = by_id[activity.start_location_id.rsplit(":", 1)[0]]
    end_sector = by_id[activity.end_location_id.rsplit(":", 1)[0]]
    low, high = sorted((start_sector.seq, end_sector.seq))
    buffered = {
        f"{sector.sector_id}:{bound}"
        for sector in sectors
        if low - rule.up_to_buffer_sectors <= sector.seq <= high + rule.up_to_buffer_sectors
    }
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
