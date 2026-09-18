"""Published penalty units (integer tenths inside CP-SAT)."""
from datetime import timedelta

CONTRACT_WEIGHTS = {1: 100, 2: 10, 3: 1}
ACTIVITY_TENTHS = {1: 13, 2: 12, 3: 10}
FORMULA_VERSION = "ps1-2026-v2"


def week_end(instance, week):
    return instance.horizon_start + timedelta(days=week * 7 - 1)


def delay_coefficient(contract, activity):
    return CONTRACT_WEIGHTS[contract.contract_priority] * ACTIVITY_TENTHS[activity.activity_priority]
