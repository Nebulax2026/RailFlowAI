"""Compatibility entry points backed by the shared A/B/C model.

Keeping a second possession model here previously allowed Scenario A to use a
weaker closure policy than the application export gate.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

from app.ps1.models import Scenario


def build_model(instance, prepared, deadline):
    from app.ps1.solver import build_scenario_model
    started = time.monotonic()
    built = build_scenario_model(instance, Scenario.A, max(0, deadline - started), started, None)
    def extract(value):
        return built.extract(SimpleNamespace(Value=value))
    return SimpleNamespace(model=built.model, x=built.x, nights=built.local_nights,
                           cost=built.primary, instance=instance, prepared=prepared, extract=extract)
