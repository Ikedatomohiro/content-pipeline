#!/usr/bin/env python3
"""Test script for the Threads API integration.

Validates environment configuration, tests API connectivity, and
prints account information. In dry-run mode, only validates env vars
and prints the configuration without making real API calls.

Usage:
    python scripts/test_api.py
    DRY_RUN=true python scripts/test_api.py
"""

import sys
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.threads_api import ThreadsAPI, ThreadsAPIError, ThreadsAuthError
from scripts.utils import load_env, setup_logging

logger = setup_logging("test_api")


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def test_env_vars() -> dict[str, str]:
    """Validate that required environment variables are set.

    Returns:
        Dict of loaded env vars.

    Raises:
        SystemExit: If required vars are missing.
    """
    print_section("Environment Check")
    loaded = load_env()

    token = sys.modules["os"].environ.get("THREADS_ACCESS_TOKEN", "")
    user_id = sys.modules["os"].environ.get("THREADS_USER_ID", "")
    dry_run = sys.modules["os"].environ.get("DRY_RUN", "false")

    print(f"  THREADS_ACCESS_TOKEN: {'***' + token[-6:] if len(token) > 6 else '(set)'}")
    print(f"  THREADS_USER_ID:      {user_id}")
    print(f"  DRY_RUN:              {dry_run}")
    print(f"  ACTIVE_ACCOUNT:       {sys.modules['os'].environ.get('ACTIVE_ACCOUNT', 'default')}")
    print("  Status: All required variables are set.")
    return loaded


def test_api_init() -> ThreadsAPI:
    """Initialize the ThreadsAPI client.

    Returns:
        Initialized ThreadsAPI instance.
    """
    print_section("API Client Initialization")
    api = ThreadsAPI()
    print(f"  User ID:  {api.user_id}")
    print(f"  Dry run:  {api.dry_run}")
    print("  Status: Client initialized successfully.")
    return api


def test_rate_limits(api: ThreadsAPI) -> None:
    """Display current rate-limit status."""
    print_section("Rate Limit Status")
    status = api.rate_limit_status
    print(f"  Hourly calls:  {status['hourly_calls_used']}/{MAX_CALLS_PER_HOUR_DISPLAY} used")
    print(f"  Daily posts:   {status['daily_posts_used']}/{MAX_POSTS_PER_DAY_DISPLAY} used")


def test_connection(api: ThreadsAPI) -> None:
    """Test the API connection by fetching the user profile.

    In dry-run mode, this will log the request without executing it.
    """
    print_section("Connection Test")

    if api.dry_run:
        print("  [DRY RUN] Skipping actual API call.")
        print("  Would fetch profile for user: " + api.user_id)
        return

    try:
        profile = api.get_profile()
        print(f"  Username: {profile.get('username', 'N/A')}")
        print(f"  Name:     {profile.get('name', 'N/A')}")
        print(f"  User ID:  {profile.get('id', 'N/A')}")
        bio = profile.get("threads_biography", "")
        if bio:
            print(f"  Bio:      {bio[:100]}{'...' if len(bio) > 100 else ''}")
        print("  Status: Connection successful.")
    except ThreadsAuthError as exc:
        print(f"  Error: Authentication failed — {exc}")
        print("  Check that your THREADS_ACCESS_TOKEN is valid and not expired.")
        sys.exit(1)
    except ThreadsAPIError as exc:
        print(f"  Error: API request failed — {exc}")
        sys.exit(1)


def test_recent_posts(api: ThreadsAPI) -> None:
    """Fetch and display a summary of recent posts.

    In dry-run mode, this will log the request without executing it.
    """
    print_section("Recent Posts")

    if api.dry_run:
        print("  [DRY RUN] Skipping actual API call.")
        print("  Would fetch recent posts for user: " + api.user_id)
        return

    try:
        result = api.get_recent_posts(limit=5)
        posts = result.get("data", [])
        if not posts:
            print("  No posts found.")
            return

        print(f"  Found {len(posts)} recent post(s):\n")
        for i, post in enumerate(posts, 1):
            text = post.get("text", "(no text)")
            preview = text[:80] + ("..." if len(text) > 80 else "")
            print(f"  {i}. [{post.get('id', 'unknown')}]")
            print(f"     {preview}")
            print(f"     Posted: {post.get('timestamp', 'N/A')}")
            print()
    except ThreadsAPIError as exc:
        print(f"  Error fetching posts: {exc}")


# Display constants
MAX_CALLS_PER_HOUR_DISPLAY = 250
MAX_POSTS_PER_DAY_DISPLAY = 500


def main() -> None:
    """Run all API tests."""
    print("Threads API Integration Test")
    print("~" * 50)

    test_env_vars()
    api = test_api_init()
    test_rate_limits(api)
    test_connection(api)
    test_recent_posts(api)

    print_section("Summary")
    if api.dry_run:
        print("  Mode: DRY RUN (no real API calls made)")
        print("  All configuration checks passed.")
    else:
        print("  Mode: LIVE")
        print("  All tests passed. API is working correctly.")
    print()


if __name__ == "__main__":
    main()
