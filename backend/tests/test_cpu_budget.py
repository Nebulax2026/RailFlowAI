from pathlib import Path

import pytest

from app.ps1 import cpu_budget
from app.ps1.strategy import SearchConfig


@pytest.mark.parametrize("cpus,expected", [(0.5, 1), (1, 1), (2, 1), (3, 2), (4, 2),
                                         (5, 4), (8, 4), (9, 8), (64, 8)])
def test_auto_selection(monkeypatch, cpus, expected):
    monkeypatch.setattr(cpu_budget, "available_cpus", lambda: cpus)
    config = SearchConfig()
    assert config.workers == "auto"
    assert config.resolved().workers == expected


@pytest.mark.parametrize("workers", range(1, 9))
def test_explicit_workers_do_not_detect_hardware(monkeypatch, workers):
    def unexpected():
        pytest.fail("Explicit worker count must bypass CPU detection")
    monkeypatch.setattr(cpu_budget, "available_cpus", unexpected)
    assert SearchConfig(workers=workers).resolved().workers == workers


@pytest.mark.parametrize("workers", [0, 9, -1, True, 2.5, None, "4", "AUTO"])
def test_invalid_workers(workers):
    with pytest.raises(ValueError, match="Workers"):
        SearchConfig(workers=workers)


def test_process_limits(monkeypatch):
    monkeypatch.setattr(cpu_budget.os, "cpu_count", lambda: 64)
    monkeypatch.setattr(cpu_budget.os, "process_cpu_count", lambda: 12, raising=False)
    monkeypatch.setattr(cpu_budget.os, "sched_getaffinity", lambda _: set(range(6)), raising=False)
    monkeypatch.setattr(cpu_budget.sys, "platform", "linux")
    monkeypatch.setattr(cpu_budget, "_cgroup_limits", lambda: iter([3.5, 2.5]))
    assert cpu_budget.available_cpus() == 2.5
    assert cpu_budget.resolve_workers() == 2


def test_unknown_cpu_count(monkeypatch):
    monkeypatch.setattr(cpu_budget.os, "cpu_count", lambda: None)
    monkeypatch.delattr(cpu_budget.os, "process_cpu_count", raising=False)
    monkeypatch.delattr(cpu_budget.os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(cpu_budget.sys, "platform", "win32")
    assert cpu_budget.resolve_workers() == 1


@pytest.mark.parametrize("version", [1, 2])
def test_cgroup_parent_and_child_quota(monkeypatch, version):
    if version == 2:
        files = {
            "/proc/self/cgroup": "0::/tenant/job",
            "/proc/self/mountinfo": "29 23 0:26 /tenant /sys/fs/cgroup rw - cgroup2 cgroup rw",
            "/sys/fs/cgroup/job/cpu.max": "400000 100000",
            "/sys/fs/cgroup/cpu.max": "150000 100000",
        }
    else:
        files = {
            "/proc/self/cgroup": "3:cpu,cpuacct:/tenant/job",
            "/proc/self/mountinfo": "29 23 0:26 /tenant /sys/fs/cgroup/cpu rw - cgroup cgroup rw,cpu,cpuacct",
            "/sys/fs/cgroup/cpu/job/cpu.cfs_quota_us": "400000",
            "/sys/fs/cgroup/cpu/job/cpu.cfs_period_us": "100000",
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "150000",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000",
        }
    files = {Path(key): value for key, value in files.items()}
    monkeypatch.setattr(cpu_budget, "_read", lambda path: files.get(path, ""))
    assert list(cpu_budget._cgroup_limits()) == [4, 1.5]


@pytest.mark.parametrize("quota", ["max 100000", "", "invalid", "100000 0"])
def test_unlimited_or_unreadable_cgroup(monkeypatch, quota):
    files = {Path("/proc/self/cgroup"): "0::/",
             Path("/proc/self/mountinfo"): "29 23 0:26 / /sys/fs/cgroup rw - cgroup2 cgroup rw",
             Path("/sys/fs/cgroup/cpu.max"): quota}
    monkeypatch.setattr(cpu_budget, "_read", lambda path: files.get(path, ""))
    assert list(cpu_budget._cgroup_limits()) == []
