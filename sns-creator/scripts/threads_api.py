#!/usr/bin/env python3
"""Core Threads API client module.

Provides the ThreadsAPI class for interacting with Meta's Threads API,
including posting, replying, fetching insights, and listing recent posts.
Supports rate limiting, retry logic, and dry-run mode.
"""

import os
import time
from typing import Any, TypedDict

import requests

from utils import load_env, setup_logging, timestamp_now

logger = setup_logging("threads_api")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://graph.threads.net/v1.0"
MAX_CALLS_PER_HOUR = 250
MAX_POSTS_PER_DAY = 500
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ThreadsAPIError(Exception):
    """Base exception for Threads API errors."""

    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class ThreadsRateLimitError(ThreadsAPIError):
    """Raised when an API rate limit is exceeded."""


class ThreadsAuthError(ThreadsAPIError):
    """Raised when authentication fails (invalid or expired token)."""


class ThreadsValidationError(ThreadsAPIError):
    """Raised when the API rejects a request due to invalid parameters."""


# ---------------------------------------------------------------------------
# Typed response dicts
# ---------------------------------------------------------------------------


class ContainerResponse(TypedDict):
    id: str


class PublishResponse(TypedDict):
    id: str


class PostResponse(TypedDict):
    container_id: str
    media_id: str


class InsightValue(TypedDict):
    value: int


class InsightEntry(TypedDict):
    name: str
    period: str
    values: list[InsightValue]
    title: str
    description: str
    id: str


class InsightsResponse(TypedDict):
    data: list[InsightEntry]


class ThreadPost(TypedDict, total=False):
    id: str
    text: str
    timestamp: str
    media_type: str
    permalink: str


class RecentPostsResponse(TypedDict):
    data: list[ThreadPost]


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class ThreadsAPI:
    """Client for the Meta Threads API.

    Reads configuration from environment variables:
        THREADS_ACCESS_TOKEN: Long-lived access token.
        THREADS_USER_ID: Numeric user/page ID.
        DRY_RUN: Set to "true" to log requests instead of executing them.

    Tracks rate limits internally and raises ThreadsRateLimitError if
    the hourly call limit or daily post limit would be exceeded.
    """

    def __init__(
        self,
        access_token: str | None = None,
        user_id: str | None = None,
    ):
        self.access_token = access_token or os.environ.get("THREADS_ACCESS_TOKEN", "")
        self.user_id = user_id or os.environ.get("THREADS_USER_ID", "")
        self.dry_run = os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")

        if not self.access_token:
            raise ThreadsAuthError("THREADS_ACCESS_TOKEN is not set")
        if not self.user_id:
            raise ThreadsValidationError("THREADS_USER_ID is not set")

        # Rate-limit tracking (in-memory, resets on restart)
        self._hourly_calls: list[float] = []
        self._daily_posts: list[float] = []

        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self.access_token}"})

        if self.dry_run:
            logger.info("DRY_RUN mode enabled — no real API calls will be made")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_rate_limit(self, is_post: bool = False) -> None:
        """Enforce in-memory rate limits before making a request.

        Args:
            is_post: Whether this call creates content (counts toward daily post limit).

        Raises:
            ThreadsRateLimitError: If the hourly or daily limit has been reached.
        """
        now = time.time()

        # Prune entries older than 1 hour
        one_hour_ago = now - 3600
        self._hourly_calls = [t for t in self._hourly_calls if t > one_hour_ago]

        if len(self._hourly_calls) >= MAX_CALLS_PER_HOUR:
            raise ThreadsRateLimitError(
                f"Hourly API call limit reached ({MAX_CALLS_PER_HOUR} calls/hour). "
                "Please wait before making more requests."
            )

        if is_post:
            one_day_ago = now - 86400
            self._daily_posts = [t for t in self._daily_posts if t > one_day_ago]
            if len(self._daily_posts) >= MAX_POSTS_PER_DAY:
                raise ThreadsRateLimitError(
                    f"Daily post limit reached ({MAX_POSTS_PER_DAY} posts/day). "
                    "Please wait before posting again."
                )

    def _record_call(self, is_post: bool = False) -> None:
        """Record a successful API call for rate-limit tracking."""
        now = time.time()
        self._hourly_calls.append(now)
        if is_post:
            self._daily_posts.append(now)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        is_post: bool = False,
    ) -> dict[str, Any]:
        """Execute an API request with rate limiting and retry logic.

        Args:
            method: HTTP method ("GET" or "POST").
            endpoint: API endpoint path (e.g., "/{user-id}/threads").
            params: Query parameters or form data.
            is_post: Whether this call creates content (for rate limiting).

        Returns:
            Parsed JSON response body.

        Raises:
            ThreadsAuthError: On 401/403 responses.
            ThreadsRateLimitError: On 429 responses or local limit exceeded.
            ThreadsValidationError: On 400 responses.
            ThreadsAPIError: On other HTTP errors after retries exhausted.
        """
        self._check_rate_limit(is_post=is_post)

        url = f"{BASE_URL}/{endpoint.lstrip('/')}"

        if self.dry_run:
            logger.info("[DRY RUN] %s %s params=%s", method, url, params)
            # Return a plausible stub response
            stub_id = f"dry_run_{int(time.time())}"
            return {"id": stub_id, "data": []}

        backoff = INITIAL_BACKOFF_SECONDS
        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if method.upper() == "GET":
                    resp = self._session.get(url, params=params, timeout=30)
                else:
                    resp = self._session.post(url, data=params, timeout=30)

                # Handle specific HTTP status codes
                if resp.status_code == 200:
                    self._record_call(is_post=is_post)
                    return resp.json()

                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = body.get("error", {}).get("message", resp.text)

                if resp.status_code in (401, 403):
                    raise ThreadsAuthError(
                        f"Authentication failed: {error_msg}",
                        status_code=resp.status_code,
                        response_body=body,
                    )

                if resp.status_code == 429:
                    raise ThreadsRateLimitError(
                        f"Rate limited by API: {error_msg}",
                        status_code=429,
                        response_body=body,
                    )

                if resp.status_code == 400:
                    raise ThreadsValidationError(
                        f"Validation error: {error_msg}",
                        status_code=400,
                        response_body=body,
                    )

                # Server errors (5xx) — retry
                if resp.status_code >= 500:
                    last_exception = ThreadsAPIError(
                        f"Server error ({resp.status_code}): {error_msg}",
                        status_code=resp.status_code,
                        response_body=body,
                    )
                    if attempt < MAX_RETRIES:
                        logger.warning(
                            "Server error on attempt %d/%d, retrying in %.1fs...",
                            attempt, MAX_RETRIES, backoff,
                        )
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    raise last_exception

                # Other client errors — don't retry
                raise ThreadsAPIError(
                    f"API error ({resp.status_code}): {error_msg}",
                    status_code=resp.status_code,
                    response_body=body,
                )

            except requests.exceptions.RequestException as exc:
                last_exception = ThreadsAPIError(f"Network error: {exc}")
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Network error on attempt %d/%d, retrying in %.1fs: %s",
                        attempt, MAX_RETRIES, backoff, exc,
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise last_exception from exc

        # Should not reach here, but just in case
        raise last_exception or ThreadsAPIError("Request failed after all retries")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def create_container(self, text: str, reply_to_id: str | None = None) -> ContainerResponse:
        """Create a media container for a text post.

        Args:
            text: Post text content (up to 500 characters).
            reply_to_id: If set, this container is a reply to the specified post.

        Returns:
            Dict with the container "id".
        """
        params: dict[str, str] = {
            "media_type": "TEXT",
            "text": text,
        }
        if reply_to_id:
            params["reply_to_id"] = reply_to_id

        logger.debug("Creating container: text=%r, reply_to=%s", text[:80], reply_to_id)
        result = self._request("POST", f"{self.user_id}/threads", params=params, is_post=False)
        return ContainerResponse(id=result["id"])

    def publish_container(self, container_id: str) -> PublishResponse:
        """Publish a previously created media container.

        Args:
            container_id: The container ID returned by create_container().

        Returns:
            Dict with the published media "id".
        """
        params = {"creation_id": container_id}
        logger.debug("Publishing container: %s", container_id)
        result = self._request("POST", f"{self.user_id}/threads_publish", params=params, is_post=True)
        return PublishResponse(id=result["id"])

    def post(self, text: str) -> PostResponse:
        """Create and publish a text post (convenience method).

        Args:
            text: Post text content.

        Returns:
            Dict with "container_id" and "media_id".
        """
        logger.info("Posting: %r", text[:80] + ("..." if len(text) > 80 else ""))
        container = self.create_container(text)
        media = self.publish_container(container["id"])
        return PostResponse(container_id=container["id"], media_id=media["id"])

    def reply(self, post_id: str, text: str) -> PostResponse:
        """Reply to an existing post.

        Args:
            post_id: The media ID of the post to reply to.
            text: Reply text content.

        Returns:
            Dict with "container_id" and "media_id".
        """
        logger.info("Replying to %s: %r", post_id, text[:80] + ("..." if len(text) > 80 else ""))
        container = self.create_container(text, reply_to_id=post_id)
        media = self.publish_container(container["id"])
        return PostResponse(container_id=container["id"], media_id=media["id"])

    def get_insights(self, media_id: str) -> InsightsResponse:
        """Fetch engagement insights for a specific post.

        Args:
            media_id: The media ID to get insights for.

        Returns:
            Dict with "data" list containing insight entries for
            views, likes, replies, quotes, reposts, and shares.
        """
        params = {
            "metric": "views,likes,replies,quotes,reposts,shares",
        }
        logger.debug("Fetching insights for: %s", media_id)
        result = self._request("GET", f"{media_id}/insights", params=params)
        return InsightsResponse(data=result.get("data", []))

    def get_recent_posts(self, limit: int = 25) -> RecentPostsResponse:
        """Fetch recent posts from the authenticated user's profile.

        Args:
            limit: Maximum number of posts to return (1-100). Defaults to 25.

        Returns:
            Dict with "data" list containing post objects.
        """
        params = {
            "fields": "id,text,timestamp,media_type,permalink",
            "limit": str(min(max(1, limit), 100)),
        }
        logger.debug("Fetching recent posts (limit=%s)", limit)
        result = self._request("GET", f"{self.user_id}/threads", params=params)
        return RecentPostsResponse(data=result.get("data", []))

    def get_profile(self) -> dict[str, Any]:
        """Fetch the authenticated user's profile information.

        Returns:
            Dict with profile fields like id, username, name, etc.
        """
        params = {
            "fields": "id,username,name,threads_profile_picture_url,threads_biography",
        }
        logger.debug("Fetching profile for user: %s", self.user_id)
        return self._request("GET", f"{self.user_id}", params=params)

    @property
    def rate_limit_status(self) -> dict[str, Any]:
        """Return current rate-limit counters and remaining capacity.

        Returns:
            Dict with hourly and daily call counts and remaining allowances.
        """
        now = time.time()
        one_hour_ago = now - 3600
        one_day_ago = now - 86400

        hourly_used = len([t for t in self._hourly_calls if t > one_hour_ago])
        daily_used = len([t for t in self._daily_posts if t > one_day_ago])

        return {
            "hourly_calls_used": hourly_used,
            "hourly_calls_remaining": MAX_CALLS_PER_HOUR - hourly_used,
            "daily_posts_used": daily_used,
            "daily_posts_remaining": MAX_POSTS_PER_DAY - daily_used,
            "checked_at": timestamp_now(),
        }


if __name__ == "__main__":
    load_env()
    api = ThreadsAPI()
    print("ThreadsAPI initialized successfully.")
    print(f"  User ID:  {api.user_id}")
    print(f"  Dry run:  {api.dry_run}")
    print(f"  Rate limits: {api.rate_limit_status}")
