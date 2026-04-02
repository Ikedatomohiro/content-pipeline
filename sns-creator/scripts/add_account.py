#!/usr/bin/env python3
"""Account setup tool — create a new account data directory from template.

Usage:
  python add_account.py ACCOUNT_NAME

Copies data/_template/ to data/ACCOUNT_NAME/ and prints next-step instructions.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import PROJECT_ROOT, setup_logging

logger = setup_logging("add_account")

VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$")


def validate_account_name(name: str) -> bool:
    """Check that the account name is lowercase alphanumeric + hyphens only."""
    if not name:
        return False
    if len(name) > 64:
        return False
    return bool(VALID_NAME_RE.match(name))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a new account data directory from template."
    )
    parser.add_argument(
        "account_name",
        help="Account name (lowercase, alphanumeric + hyphens only).",
    )
    args = parser.parse_args()

    name = args.account_name.lower().strip()

    if not validate_account_name(name):
        print(
            f"Error: Invalid account name '{name}'.\n"
            "  - Must be lowercase\n"
            "  - Only alphanumeric characters and hyphens\n"
            "  - Cannot start or end with a hyphen\n"
            "  - Maximum 64 characters",
            file=sys.stderr,
        )
        sys.exit(1)

    template_dir = PROJECT_ROOT / "data" / "_template"
    target_dir = PROJECT_ROOT / "data" / name

    if not template_dir.exists():
        print(
            f"Error: Template directory not found at {template_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    if target_dir.exists():
        print(
            f"Error: Account directory already exists at {target_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Copy template to new account
    shutil.copytree(template_dir, target_dir)
    logger.info("Created account directory: %s", target_dir)

    # Print instructions
    print(f"\nAccount '{name}' created successfully!")
    print(f"  Directory: {target_dir}")
    print()
    print("Next steps:")
    print(f"  1. Edit knowledge files in data/{name}/knowledge/")
    print(f"     - brand_voice.json   : tone, style, vocabulary")
    print(f"     - themes.json        : content themes and topics")
    print(f"     - patterns.json      : post patterns / templates")
    print()
    print(f"  2. Set environment variables:")
    print(f"     export ACTIVE_ACCOUNT={name}")
    print(f"     export THREADS_ACCESS_TOKEN=your_token_here")
    print(f"     export THREADS_USER_ID=your_user_id_here")
    print()
    print(f"  3. Test the setup:")
    print(f"     cd scripts && python run_supervisor.py --check-only")
    print()


if __name__ == "__main__":
    main()
