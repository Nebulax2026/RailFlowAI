"""Conservative CP-SAT worker selection for the process running the solver."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeError):
        return ""


def _cgroup_limits():
    """Read v1/v2 CPU quotas, including visible parent group limits."""
    groups = {}
    for line in _read(Path("/proc/self/cgroup")).splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3:
            for controller in fields[1].split(","):
                groups[controller] = fields[2]
    for line in _read(Path("/proc/self/mountinfo")).splitlines():
        before, separator, after = line.partition(" - ")
        fields, mounted = before.split(), after.split()
        if not separator or len(fields) < 5 or len(mounted) < 3:
            continue
        version = mounted[0]
        controller = "" if version == "cgroup2" else "cpu"
        if version not in {"cgroup", "cgroup2"} or controller not in groups:
            continue
        if version == "cgroup" and "cpu" not in mounted[2].split(","):
            continue
        # mountinfo escapes whitespace and backslashes in path names.
        def unescape(value):
            for code, character in (("040", " "), ("011", "\t"), ("012", "\n"), ("134", "\\")):
                value = value.replace("\\" + code, character)
            return value
        root, mount = Path(unescape(fields[3])), Path(unescape(fields[4]))
        group = Path(groups[controller])
        try:
            relative = group.relative_to(root)
        except ValueError:
            # A cgroup namespace can expose membership relative to its root.
            relative = group.relative_to("/")
        if ".." in relative.parts:
            relative = Path(".")
        directory = mount / relative
        while True:
            try:
                if version == "cgroup2":
                    quota, period = _read(directory / "cpu.max").split()
                else:
                    quota = _read(directory / "cpu.cfs_quota_us")
                    period = _read(directory / "cpu.cfs_period_us")
                quota, period = int(quota), int(period)
                if quota > 0 and period > 0:
                    yield quota / period
            except ValueError:
                pass  # Missing, unlimited, or malformed quota.
            if directory == mount:
                break
            directory = directory.parent


def available_cpus() -> float:
    limits = [float(os.cpu_count() or 1)]
    process_count = getattr(os, "process_cpu_count", None)
    if process_count is not None:
        count = process_count()
        if count:
            limits.append(float(count))
    try:
        limits.append(float(len(os.sched_getaffinity(0))))
    except (AttributeError, OSError):
        pass
    if sys.platform.startswith("linux"):
        limits.extend(_cgroup_limits())
    return max(0.01, min(limits))


def validate_workers(workers: int | str) -> None:
    if workers != "auto" and (type(workers) is not int or not 1 <= workers <= 8):
        raise ValueError("Workers must be 'auto' or an integer from 1 to 8.")


def resolve_workers(workers: int | str = "auto") -> int:
    validate_workers(workers)
    if workers != "auto":
        return workers
    cpus = available_cpus()
    if cpus <= 2:
        return 1
    if cpus <= 4:
        return 2
    if cpus <= 8:
        return 4
    return 8
