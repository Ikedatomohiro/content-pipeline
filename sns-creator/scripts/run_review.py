#!/usr/bin/env python3
"""Human review CLI for the 5% check model.

Commands:
  python run_review.py list                  — show all drafts in pool
  python run_review.py approve DRAFT_ID      — move draft to queue
  python run_review.py approve-all           — approve all drafts with score >= 8.0
  python run_review.py reject DRAFT_ID       — mark draft as rejected
  python run_review.py stats                 — show draft pool statistics
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    generate_id,
    get_account_path,
    load_env,
    load_json,
    save_json,
    setup_logging,
    timestamp_now,
)

logger = setup_logging("run_review")

# ANSI color codes
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def load_drafts() -> list[dict]:
    """Load all drafts from the draft pool."""
    drafts_dir = get_account_path("drafts")
    drafts = []
    if drafts_dir.is_dir():
        for f in sorted(drafts_dir.glob("*.json")):
            try:
                draft = load_json(f)
                draft["_file"] = f
                drafts.append(draft)
            except Exception as exc:
                logger.warning("Failed to load %s: %s", f, exc)
    return drafts


def load_queue() -> list[dict]:
    """Load the posting queue."""
    queue_path = get_account_path("queue/queue.json")
    if queue_path.exists():
        return load_json(queue_path)
    return []


def save_queue(queue: list[dict]) -> None:
    """Save the posting queue."""
    queue_path = get_account_path("queue/queue.json")
    save_json(queue_path, queue)


def score_color(score: float) -> str:
    """Return ANSI color based on score threshold."""
    if score >= 8.0:
        return GREEN
    elif score >= 7.0:
        return YELLOW
    return RED


def status_color(status: str) -> str:
    """Return ANSI color based on draft status."""
    colors = {
        "pending": CYAN,
        "approved": GREEN,
        "rejected": RED,
        "queued": GREEN,
    }
    return colors.get(status, RESET)


def truncate(text: str, length: int = 80) -> str:
    """Truncate text to a max length, adding ellipsis if needed."""
    if not text:
        return ""
    # Collapse newlines for display
    text = text.replace("\n", " ").strip()
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


def cmd_list(args: argparse.Namespace) -> None:
    """Show all drafts in the pool."""
    drafts = load_drafts()
    if not drafts:
        print("No drafts in pool.")
        return

    print(f"\n{BOLD}Draft Pool ({len(drafts)} drafts){RESET}")
    print(f"{'ID':<12} {'Score':>5}  {'Status':<10} {'Pattern':<20} {'Theme':<15} {'Text'}")
    print("-" * 120)

    for d in drafts:
        draft_id = d.get("id", "?")[:10]
        score = d.get("score", 0.0)
        status = d.get("status", "pending")
        pattern = truncate(d.get("pattern", ""), 18)
        theme = truncate(d.get("theme", ""), 13)
        text = truncate(d.get("text", ""), 80)

        sc = score_color(score)
        stc = status_color(status)

        print(
            f"{draft_id:<12} {sc}{score:>5.1f}{RESET}  "
            f"{stc}{status:<10}{RESET} {pattern:<20} {theme:<15} "
            f"{DIM}{text}{RESET}"
        )

    print()


def cmd_approve(args: argparse.Namespace) -> None:
    """Move a specific draft to the posting queue."""
    draft_id = args.draft_id
    drafts = load_drafts()
    target = None
    for d in drafts:
        if d.get("id", "").startswith(draft_id):
            target = d
            break

    if not target:
        print(f"Draft not found: {draft_id}")
        sys.exit(1)

    # Update draft status
    target["status"] = "queued"
    target["approved_at"] = timestamp_now()
    draft_file = target.pop("_file")
    save_json(draft_file, target)

    # Add to queue
    queue = load_queue()
    queue_entry = {
        "id": target.get("id", generate_id()),
        "text": target.get("text", ""),
        "pattern": target.get("pattern", ""),
        "theme": target.get("theme", ""),
        "score": target.get("score", 0.0),
        "source": "review_approved",
        "queued_at": timestamp_now(),
        "status": "pending",
    }
    queue.append(queue_entry)
    save_queue(queue)

    print(f"{GREEN}Approved{RESET} draft {draft_id[:10]} and added to queue.")


def cmd_approve_all(args: argparse.Namespace) -> None:
    """Approve all drafts with score >= 8.0."""
    drafts = load_drafts()
    approved = 0
    queue = load_queue()

    for d in drafts:
        if d.get("status", "pending") != "pending":
            continue
        if d.get("score", 0.0) < 8.0:
            continue

        d["status"] = "queued"
        d["approved_at"] = timestamp_now()
        draft_file = d.pop("_file")
        save_json(draft_file, d)

        queue_entry = {
            "id": d.get("id", generate_id()),
            "text": d.get("text", ""),
            "pattern": d.get("pattern", ""),
            "theme": d.get("theme", ""),
            "score": d.get("score", 0.0),
            "source": "review_approved_batch",
            "queued_at": timestamp_now(),
            "status": "pending",
        }
        queue.append(queue_entry)
        approved += 1

    save_queue(queue)
    print(f"{GREEN}Approved {approved} drafts{RESET} with score >= 8.0 and added to queue.")


def cmd_reject(args: argparse.Namespace) -> None:
    """Mark a draft as rejected."""
    draft_id = args.draft_id
    drafts = load_drafts()
    target = None
    for d in drafts:
        if d.get("id", "").startswith(draft_id):
            target = d
            break

    if not target:
        print(f"Draft not found: {draft_id}")
        sys.exit(1)

    target["status"] = "rejected"
    target["rejected_at"] = timestamp_now()
    draft_file = target.pop("_file")
    save_json(draft_file, target)

    print(f"{RED}Rejected{RESET} draft {draft_id[:10]}.")


def cmd_stats(args: argparse.Namespace) -> None:
    """Show draft pool statistics."""
    drafts = load_drafts()
    if not drafts:
        print("No drafts in pool.")
        return

    total = len(drafts)
    by_status: dict[str, int] = {}
    scores: list[float] = []
    by_pattern: dict[str, int] = {}
    by_theme: dict[str, int] = {}

    for d in drafts:
        status = d.get("status", "pending")
        by_status[status] = by_status.get(status, 0) + 1

        score = d.get("score", 0.0)
        scores.append(score)

        pattern = d.get("pattern", "unknown")
        by_pattern[pattern] = by_pattern.get(pattern, 0) + 1

        theme = d.get("theme", "unknown")
        by_theme[theme] = by_theme.get(theme, 0) + 1

    avg_score = sum(scores) / len(scores) if scores else 0.0
    high_score = len([s for s in scores if s >= 8.0])

    queue = load_queue()
    pending_queue = len([q for q in queue if q.get("status") == "pending"])

    print(f"\n{BOLD}Draft Pool Statistics{RESET}")
    print(f"  Total drafts:     {total}")
    print(f"  Average score:    {avg_score:.1f}")
    print(f"  High score (>=8): {GREEN}{high_score}{RESET}")
    print(f"  Queue pending:    {pending_queue}")

    print(f"\n{BOLD}By Status:{RESET}")
    for status, count in sorted(by_status.items()):
        c = status_color(status)
        print(f"  {c}{status:<12}{RESET} {count}")

    print(f"\n{BOLD}By Pattern:{RESET}")
    for pattern, count in sorted(by_pattern.items(), key=lambda x: -x[1]):
        print(f"  {pattern:<25} {count}")

    print(f"\n{BOLD}By Theme:{RESET}")
    for theme, count in sorted(by_theme.items(), key=lambda x: -x[1]):
        print(f"  {theme:<25} {count}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Human review CLI for draft management."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list
    subparsers.add_parser("list", help="Show all drafts in pool")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a specific draft")
    approve_parser.add_argument("draft_id", help="Draft ID (or prefix)")

    # approve-all
    subparsers.add_parser("approve-all", help="Approve all drafts with score >= 8.0")

    # reject
    reject_parser = subparsers.add_parser("reject", help="Reject a specific draft")
    reject_parser.add_argument("draft_id", help="Draft ID (or prefix)")

    # stats
    subparsers.add_parser("stats", help="Show draft pool statistics")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load env (no API keys required for review)
    load_env(required_vars=[])

    commands = {
        "list": cmd_list,
        "approve": cmd_approve,
        "approve-all": cmd_approve_all,
        "reject": cmd_reject,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
