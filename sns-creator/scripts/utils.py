#!/usr/bin/env python3
"""Shared utilities for the Threads API integration.

Provides common helpers for file I/O, logging, environment loading,
path resolution, and ID generation used across all scripts.
"""

import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Project root is one level up from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Data root: override with DATA_ROOT env var (used in CI to point at content-data submodule)
DATA_ROOT = Path(os.environ.get("DATA_ROOT", str(PROJECT_ROOT / "data")))


def load_env(required_vars: list[str] | None = None) -> dict[str, str]:
    """Load environment variables from .env file and validate required vars.

    Searches for .env in the project root directory. Variables already set
    in the environment take precedence over .env file values.

    Args:
        required_vars: List of environment variable names that must be set.
            Defaults to ["THREADS_ACCESS_TOKEN", "THREADS_USER_ID"].

    Returns:
        Dictionary of all loaded environment variables from the .env file.

    Raises:
        SystemExit: If any required variables are missing.
    """
    if required_vars is None:
        required_vars = ["THREADS_ACCESS_TOKEN", "THREADS_USER_ID"]

    env_path = PROJECT_ROOT / ".env"
    loaded: dict[str, str] = {}

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes if present
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                loaded[key] = value
                # Only set in environment if not already defined
                if key not in os.environ:
                    os.environ[key] = value

    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        print(f"Set them in your environment or in {env_path}", file=sys.stderr)
        sys.exit(1)

    return loaded


def setup_logging(name: str, level: int | None = None, verbose: bool = False) -> logging.Logger:
    """Configure and return a logger with consistent formatting.

    Args:
        name: Logger name, typically the module name.
        level: Logging level. Defaults to DEBUG if LOG_LEVEL env var is
            "DEBUG", otherwise INFO.
        verbose: If True, force DEBUG level regardless of env var.

    Returns:
        Configured logger instance.
    """
    if verbose:
        level = logging.DEBUG
    elif level is None:
        env_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, env_level, logging.INFO)

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def get_account_path(subpath: str) -> Path:
    """Resolve a path under the active account's data directory.

    Uses the ACTIVE_ACCOUNT environment variable to determine the account
    directory. Falls back to "default" if not set.

    Args:
        subpath: Relative path within the account directory (e.g., "posts/queue.json").

    Returns:
        Absolute Path object for the resolved location.
    """
    account = os.environ.get("ACTIVE_ACCOUNT", "default")
    path = DATA_ROOT / account / subpath
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


_MISSING = object()


def load_json(path: str | Path, default: Any = _MISSING) -> Any:
    """Load and parse a JSON file.

    Args:
        path: Path to the JSON file.
        default: Value to return if the file does not exist. If omitted,
            raises FileNotFoundError when the file is missing.

    Returns:
        Parsed JSON data (dict, list, or other JSON-compatible type).

    Raises:
        FileNotFoundError: If the file does not exist and no default is given.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    file_path = Path(path)
    if not file_path.exists():
        if default is not _MISSING:
            return default
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, data: Any, indent: int = 2) -> None:
    """Atomically write data to a JSON file.

    Writes to a temporary file in the same directory, then renames it to
    the target path. This prevents corruption from interrupted writes.

    Args:
        path: Destination file path.
        data: JSON-serializable data to write.
        indent: JSON indentation level. Defaults to 2.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory for atomic rename
    fd, tmp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f".{file_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, file_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def timestamp_now() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Returns:
        Timestamp string like "2026-03-25T14:30:00+00:00".
    """
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix: str = "") -> str:
    """Generate a random UUID4 string, optionally with a prefix.

    Args:
        prefix: Optional prefix to prepend (e.g., "draft", "research").

    Returns:
        ID string like "draft_a1b2c3d4-e5f6-7890-abcd-ef1234567890".
    """
    uid = str(uuid.uuid4())
    return f"{prefix}_{uid}" if prefix else uid


if __name__ == "__main__":
    # Quick self-test of utilities
    logger = setup_logging("utils_test")
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Timestamp: %s", timestamp_now())
    logger.info("Generated ID: %s", generate_id())

    test_data = {"test": True, "timestamp": timestamp_now()}
    test_path = PROJECT_ROOT / "data" / ".utils_test.json"
    save_json(test_path, test_data)
    loaded = load_json(test_path)
    assert loaded == test_data, "JSON round-trip failed"
    test_path.unlink()
    logger.info("All utility self-tests passed.")
