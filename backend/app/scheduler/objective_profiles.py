from app.domain.enums import ScheduleOption


OBJECTIVE_PROFILES = {
    ScheduleOption.MINIMUM_DISRUPTION: {
        "approved_change": 100,
        "overtime": 10,
        "priority_delay": 20,
        "completion": 10,
    },
    ScheduleOption.MINIMUM_OVERTIME: {
        "approved_change": 30,
        "overtime": 100,
        "priority_delay": 20,
        "completion": 10,
    },
    ScheduleOption.MAXIMUM_COMPLETION: {
        "approved_change": 20,
        "overtime": 20,
        "priority_delay": 20,
        "completion": 100,
    },
    ScheduleOption.CRITICAL_WORK_FIRST: {
        "approved_change": 20,
        "overtime": 20,
        "priority_delay": 100,
        "completion": 10,
    },
}
