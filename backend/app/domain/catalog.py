from __future__ import annotations

TRACK_SECTORS = ["T08", "T09", "T10", "T11", "T12", "T13", "T14"]

WORK_TYPES = [
    "inspection",
    "electrical",
    "track",
    "signal_replacement",
    "signal_test",
    "track_inspection",
    "track_renewal",
    "power_isolation",
    "electrical_repair",
    "safety_clearance",
    "service_restore",
    "emergency",
]

CREWS = ["E1", "E2", "TG1", "TG2", "MECH1", "MECH2", "SIG1", "SIG2", "SAFE1"]

EQUIPMENT = [
    "SignalKit-1",
    "SignalKit-2",
    "GeometryCar-1",
    "GeometryCar-2",
    "PowerUnit-1",
    "PowerUnit-2",
    "DiagnosticKit-1",
    "RailGrinder-1",
    "IsolationKit-1",
]

PRIORITIES = [1, 2, 3, 4, 5]

USER_ROLES = ["requester", "approver", "schedule_manager"]


def catalog_response() -> dict[str, list[str] | list[int]]:
    return {
        "track_sectors": TRACK_SECTORS,
        "work_types": WORK_TYPES,
        "crews": CREWS,
        "equipment": EQUIPMENT,
        "priorities": PRIORITIES,
        "user_roles": USER_ROLES,
    }
