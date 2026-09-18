"""Run from backend: .venv/bin/python -m app.ps1.strategy_cli --help."""
from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import sys
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path

# Keep numerical-library thread pools from multiplying the configured CP-SAT
# CPU budget or reserving many thread stacks under the Linux memory limit.
for _thread_limit_name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_thread_limit_name] = "1"

from app.ps1.exporter import scenario_csvs
from app.ps1.models import Scenario
from app.ps1.parser import EXPECTED_FILES, parse_instance
from app.ps1.strategy import SearchConfig
from app.ps1.scenario_search import solve as solve_shared

ROOT = Path(__file__).resolve().parents[4]


def atomic_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n")
    temporary.replace(path)


def save_solution(output: Path, solution, diagnostics) -> None:
    # Publish one manifest only after all files of a generation are complete.
    generation = f"incumbent-{len(diagnostics.get('trajectory', [])):04d}"
    directory = output / generation
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in scenario_csvs(solution).items():
        (directory / name).write_bytes(content)
    atomic_json(directory / "validation.json", asdict(solution.validation))
    atomic_json(output / "checkpoint.json", {"directory": generation, "diagnostics": diagnostics})


def main(argv=None):
    started = time.monotonic()
    parser = argparse.ArgumentParser(description="Select a search strategy and solve one PS1 scenario.")
    parser.add_argument("--scenario", choices=("A", "B", "C"), default="A")
    parser.add_argument("--input", type=Path, default=ROOT / "PS1/01_data")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--strategy", choices=("integrated", "random_lns", "alns"))
    parser.add_argument("--initialization", choices=("direct", "feasibility"))
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--workers", choices=("auto", *map(str, range(1, 9))),
                        help="auto (default): select 1/2/4/8 workers from available CPUs; or set 1-8")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--memory-limit-mb", type=int)
    args = parser.parse_args(argv)
    values = json.loads(args.config.read_text()) if args.config else {}
    for argument, field in (("strategy", "strategy"), ("initialization", "initialization"), ("seconds", "time_limit_seconds"),
                            ("workers", "workers"), ("seed", "seed"), ("memory_limit_mb", "memory_limit_mb")):
        if getattr(args, argument) is not None:
            value = getattr(args, argument)
            values[field] = int(value) if field == "workers" and value != "auto" else value
    args.output.mkdir(parents=True, exist_ok=True)
    # Never accidentally publish an incumbent from a previous invocation.
    if (args.output / "checkpoint.json").exists():
        parser.error("Output already contains a run. Choose a new output directory.")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        config = SearchConfig(**values).resolved()
        memory_enforcement = "CP-SAT advisory limit; no portable OS address-space cap"
        if sys.platform.startswith("linux"):
            import resource
            ceiling = config.memory_limit_mb * 1024**2
            resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
            memory_enforcement = "Linux RLIMIT_AS process address-space limit"
        instance = parse_instance({name: (args.input / name).read_bytes() for name in EXPECTED_FILES})
        remaining = config.time_limit_seconds - (time.monotonic() - started)
        if remaining < 0.2:
            raise TimeoutError("Input parsing exhausted the total budget.")
        callback = lambda s, d: save_solution(args.output, s, d)
        result = solve_shared(instance, Scenario(args.scenario), replace(config, time_limit_seconds=remaining), stop.is_set, callback)
        if result.solution:
            save_solution(args.output, result.solution, result.diagnostics)
            for name, content in scenario_csvs(result.solution).items():
                (args.output / name).write_bytes(content)
            atomic_json(args.output / "validation.json", asdict(result.solution.validation))
        result.diagnostics.update(config=asdict(config), python_version=platform.python_version(),
                                  platform=platform.platform(), cpu_count=os.cpu_count(), memory_enforcement=memory_enforcement)
        result.diagnostics["total_elapsed_seconds"] = time.monotonic() - started
        atomic_json(args.output / "diagnostics.json", result.diagnostics)
        print(json.dumps({k: result.diagnostics[k] for k in ("status", "objective", "global_lower_bound", "total_elapsed_seconds")}), flush=True)
        return 0 if result.solution and result.diagnostics["status"] != "input_or_model_error" else 2
    except (ValueError, OSError, TimeoutError, MemoryError) as exc:
        atomic_json(args.output / "diagnostics.json", {"status": "input_or_model_error", "error": str(exc), "total_elapsed_seconds": time.monotonic() - started})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


