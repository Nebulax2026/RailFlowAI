"""Run a selected method on all 30 synthetic cases and save raw/average scores."""
import argparse
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import ortools
from app.ps1.benchmark import BENCHMARK_WORKERS, METHODS, benchmark_manager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", choices=(*METHODS, "all"), default="integrated")
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.output.exists(): parser.error("Choose a new output file.")
    if not 5 <= args.seconds <= 120: parser.error("Use 5–120 seconds per case.")
    run = benchmark_manager.create(args.method, args.seconds, args.seed)
    while True:
        result = benchmark_manager.get(run["id"])
        if result["status"] not in ("queued", "running"):
            break
        time.sleep(.2)
    payload = dict(platform=platform.platform(), python=platform.python_version(),
                   ortools=ortools.__version__, cp_sat_workers_per_run=BENCHMARK_WORKERS,
                   run=result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2)+"\n")
    print(json.dumps(dict(status=result["status"], summary=result["summary"]), indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
