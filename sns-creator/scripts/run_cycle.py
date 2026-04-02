#!/usr/bin/env python3
"""Main cycle orchestrator — runs the full daily pipeline.

Steps executed in order:
  1. supervisor  — health check (abort if kill switch active)
  2. fetcher     — fetch metrics for posts needing measurement
  3. analyst     — analyze data and generate writer instructions
  4. researcher  — identify research gaps
  5. writer      — generate drafts

Usage:
  python run_cycle.py                 # run full cycle
  python run_cycle.py --dry-run       # pass --dry-run to every sub-script
  python run_cycle.py --step fetcher  # run only the fetcher step
  python run_cycle.py --skip writer   # skip the writer step
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from the scripts package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    PROJECT_ROOT,
    get_account_path,
    load_env,
    save_json,
    setup_logging,
    timestamp_now,
)

logger = setup_logging("run_cycle")

# Ordered pipeline steps — each entry is (name, script, extra_args)
STEPS = [
    ("supervisor", "run_supervisor.py", ["--check-only"]),
    ("fetcher", "run_fetcher.py", []),
    ("analyst", "run_analyst.py", []),
    ("researcher", "run_researcher.py", []),
    ("writer", "run_writer.py", []),
]

SCRIPTS_DIR = Path(__file__).resolve().parent


def run_step(
    name: str,
    script: str,
    extra_args: list[str],
    dry_run: bool = False,
) -> dict:
    """Execute a single pipeline step as a subprocess.

    Returns a result dict with timing and status information.
    """
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + extra_args
    if dry_run:
        cmd.append("--dry-run")

    logger.info("=== Step [%s] starting: %s ===", name, " ".join(cmd))
    start = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10-minute timeout per step
        )
        elapsed = round(time.monotonic() - start, 2)

        if result.stdout:
            for line in result.stdout.strip().splitlines():
                logger.info("  [%s stdout] %s", name, line)
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                logger.info("  [%s stderr] %s", name, line)

        if result.returncode != 0:
            logger.error(
                "Step [%s] FAILED (exit code %d) after %.2fs",
                name,
                result.returncode,
                elapsed,
            )
            return {
                "step": name,
                "status": "failed",
                "exit_code": result.returncode,
                "elapsed_seconds": elapsed,
                "error": result.stderr[-500:] if result.stderr else "",
            }

        logger.info("Step [%s] completed successfully in %.2fs", name, elapsed)
        return {
            "step": name,
            "status": "success",
            "exit_code": 0,
            "elapsed_seconds": elapsed,
        }

    except subprocess.TimeoutExpired:
        elapsed = round(time.monotonic() - start, 2)
        logger.error("Step [%s] TIMED OUT after %.2fs", name, elapsed)
        return {
            "step": name,
            "status": "timeout",
            "exit_code": -1,
            "elapsed_seconds": elapsed,
            "error": "Process timed out after 600 seconds",
        }
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 2)
        logger.error("Step [%s] raised exception: %s", name, exc)
        return {
            "step": name,
            "status": "error",
            "exit_code": -1,
            "elapsed_seconds": elapsed,
            "error": str(exc),
        }


def run_cycle(
    dry_run: bool = False,
    only_step: str | None = None,
    skip_steps: list[str] | None = None,
) -> dict:
    """Execute the full cycle pipeline.

    Args:
        dry_run: Pass --dry-run to all sub-scripts.
        only_step: If set, run only this specific step.
        skip_steps: List of step names to skip.

    Returns:
        Cycle log dictionary.
    """
    skip_steps = skip_steps or []
    cycle_start = time.monotonic()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    cycle_log = {
        "date": today,
        "started_at": timestamp_now(),
        "dry_run": dry_run,
        "only_step": only_step,
        "skip_steps": skip_steps,
        "steps": [],
        "status": "running",
    }

    steps_to_run = STEPS
    if only_step:
        matched = [s for s in STEPS if s[0] == only_step]
        if not matched:
            valid = [s[0] for s in STEPS]
            logger.error("Unknown step '%s'. Valid steps: %s", only_step, valid)
            cycle_log["status"] = "error"
            cycle_log["error"] = f"Unknown step: {only_step}"
            return cycle_log
        steps_to_run = matched

    for name, script, extra_args in steps_to_run:
        if name in skip_steps:
            logger.info("Skipping step [%s] (--skip)", name)
            cycle_log["steps"].append({
                "step": name,
                "status": "skipped",
                "elapsed_seconds": 0,
            })
            continue

        step_result = run_step(name, script, extra_args, dry_run=dry_run)
        cycle_log["steps"].append(step_result)

        # exit code 2 はソフト警告（データ不足など）— パイプラインは継続
        if step_result["exit_code"] == 2:
            logger.warning(
                "Step [%s] returned warning (exit code 2) — continuing pipeline",
                name,
            )
            step_result["status"] = "warning"
            continue

        if step_result["status"] != "success":
            logger.error(
                "Pipeline stopped: step [%s] failed with status '%s'",
                name,
                step_result["status"],
            )
            cycle_log["status"] = "failed"
            cycle_log["failed_step"] = name
            break
    else:
        cycle_log["status"] = "success"

    total_elapsed = round(time.monotonic() - cycle_start, 2)
    cycle_log["completed_at"] = timestamp_now()
    cycle_log["total_elapsed_seconds"] = total_elapsed

    logger.info(
        "Cycle finished: status=%s, total_time=%.2fs",
        cycle_log["status"],
        total_elapsed,
    )

    return cycle_log


def save_cycle_log(cycle_log: dict) -> Path:
    """Write the cycle log to the account's logs directory."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_path = get_account_path(f"logs/cycle_{today}.json")
    save_json(log_path, cycle_log)
    logger.info("Cycle log saved to %s", log_path)
    return log_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full daily cycle pipeline."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to all sub-scripts.",
    )
    parser.add_argument(
        "--step",
        type=str,
        default=None,
        choices=[s[0] for s in STEPS],
        help="Run only this specific step.",
    )
    parser.add_argument(
        "--skip",
        type=str,
        action="append",
        default=[],
        help="Skip a specific step (can be repeated).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load env — cycle orchestrator only needs ACTIVE_ACCOUNT
    load_env(required_vars=[])

    logger.info("Starting daily cycle (dry_run=%s)", args.dry_run)

    cycle_log = run_cycle(
        dry_run=args.dry_run,
        only_step=args.step,
        skip_steps=args.skip,
    )

    save_cycle_log(cycle_log)

    if cycle_log["status"] != "success":
        logger.error("Cycle did not complete successfully.")
        sys.exit(1)

    logger.info("Cycle completed successfully.")


if __name__ == "__main__":
    main()
