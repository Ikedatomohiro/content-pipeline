#!/usr/bin/env python3
"""
Fetcher Agent — メトリクス取得エージェント

投稿済みポストのエンゲージメントメトリクス（1h/6h/24h）を取得する。
Threads APIからインサイトデータを取得し、posts.jsonに保存する。
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# スクリプトディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_json, save_json, setup_logging, timestamp_now, PROJECT_ROOT
from threads_api import ThreadsAPI

# メトリクス取得タイミング（投稿からの経過時間）
METRIC_WINDOWS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
}

# 許容誤差（早すぎる取得を防ぐ）
WINDOW_TOLERANCE = timedelta(minutes=5)

# 遅延許容（この時間を超えたらスキップ）
WINDOW_MAX_DELAY = {
    "1h": timedelta(hours=2),
    "6h": timedelta(hours=8),
    "24h": timedelta(hours=30),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Fetcher Agent: メトリクス取得")
    parser.add_argument("--account", "-a", default=os.environ.get("ACTIVE_ACCOUNT", "default"), help="アカウントID")
    parser.add_argument("--dry-run", action="store_true", help="実際のAPI呼び出しを行わない")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    return parser.parse_args()


def find_posts_needing_metrics(posts: list, logger) -> list:
    """メトリクス取得が必要なポストを特定する"""
    needs_fetch = []
    now = datetime.now(timezone.utc)

    for post in posts:
        # 投稿済みでないものはスキップ
        if post.get("status") != "posted":
            continue

        posted_at_str = post.get("posted_at")
        if not posted_at_str:
            continue

        try:
            posted_at = datetime.fromisoformat(posted_at_str)
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning(f"投稿日時のパースに失敗: post_id={post.get('id')}, posted_at={posted_at_str}")
            continue

        elapsed = now - posted_at
        metrics = post.get("metrics", {})

        for window_name, window_delta in METRIC_WINDOWS.items():
            # 既に取得済みならスキップ
            if window_name in metrics:
                continue

            # 十分な時間が経過しているか
            if elapsed >= (window_delta - WINDOW_TOLERANCE):
                # 遅延が大きすぎる場合はスキップ（ログは出す）
                max_delay = WINDOW_MAX_DELAY[window_name]
                if elapsed > max_delay:
                    logger.debug(
                        f"メトリクス取得期限超過: post_id={post.get('id')}, "
                        f"window={window_name}, elapsed={elapsed}"
                    )
                    continue

                needs_fetch.append({
                    "post": post,
                    "window": window_name,
                    "elapsed": elapsed,
                })

    return needs_fetch


def fetch_metrics_for_post(api: ThreadsAPI, post: dict, window: str, logger, dry_run: bool = False) -> dict | None:
    """1つのポストのメトリクスを取得する"""
    threads_post_id = post.get("threads_post_id")
    if not threads_post_id:
        logger.warning(f"Threads投稿IDが見つからない: post_id={post.get('id')}")
        return None

    if dry_run:
        logger.info(f"[DRY-RUN] メトリクス取得: post_id={post.get('id')}, window={window}")
        return {
            "views": 0,
            "likes": 0,
            "replies": 0,
            "reposts": 0,
            "quotes": 0,
            "saves": 0,
            "fetched_at": timestamp_now(),
        }

    try:
        insights = api.get_insights(threads_post_id)
        return {
            "views": insights.get("views", 0),
            "likes": insights.get("likes", 0),
            "replies": insights.get("replies", 0),
            "reposts": insights.get("reposts", 0),
            "quotes": insights.get("quotes", 0),
            "saves": insights.get("saves", 0),
            "fetched_at": timestamp_now(),
        }
    except Exception as e:
        logger.error(f"メトリクス取得エラー: post_id={post.get('id')}, error={e}")
        return None


def main():
    args = parse_args()
    logger = setup_logging("fetcher", verbose=args.verbose)

    logger.info("=== Fetcher Agent 開始 ===")
    if args.dry_run:
        logger.info("[DRY-RUN モード]")

    # パス設定
    account_path = PROJECT_ROOT / "data" / args.account
    account_path.mkdir(parents=True, exist_ok=True)
    posts_path = account_path / "history" / "posts.json"
    supervisor_log_path = account_path / "logs" / "supervisor.json"

    # 投稿データ読み込み
    posts_data = load_json(posts_path, default={"posts": []})
    posts = posts_data.get("posts", [])

    if not posts:
        logger.info("投稿データなし。終了します。")
        return 0

    # メトリクス取得が必要なポストを特定
    needs_fetch = find_posts_needing_metrics(posts, logger)

    if not needs_fetch:
        logger.info("メトリクス取得が必要なポストはありません。")
        return 0

    logger.info(f"メトリクス取得対象: {len(needs_fetch)}件")

    # API初期化
    api = ThreadsAPI()

    # メトリクス取得
    consecutive_errors = 0
    success_count = 0
    error_count = 0

    # ポストIDからインデックスへのマッピング
    post_index = {p.get("id"): i for i, p in enumerate(posts)}

    for item in needs_fetch:
        post = item["post"]
        window = item["window"]
        post_id = post.get("id")

        logger.info(f"メトリクス取得中: post_id={post_id}, window={window}")

        metrics = fetch_metrics_for_post(api, post, window, logger, dry_run=args.dry_run)

        if metrics is None:
            consecutive_errors += 1
            error_count += 1

            # 3回連続エラーで停止
            if consecutive_errors >= 3:
                error_msg = f"3回連続APIエラーにより停止: last_post_id={post_id}"
                logger.error(error_msg)

                # スーパーバイザーログに記録
                supervisor_log = load_json(supervisor_log_path, default={"errors": [], "warnings": []})
                supervisor_log["errors"].append({
                    "agent": "fetcher",
                    "message": error_msg,
                    "timestamp": timestamp_now(),
                    "consecutive_errors": consecutive_errors,
                })
                save_json(supervisor_log_path, supervisor_log)

                # 途中までの結果を保存
                posts_data["posts"] = posts
                posts_data["last_fetch_run"] = timestamp_now()
                save_json(posts_path, posts_data)

                return 1
        else:
            consecutive_errors = 0
            success_count += 1

            # ポストデータを更新
            idx = post_index.get(post_id)
            if idx is not None:
                if "metrics" not in posts[idx]:
                    posts[idx]["metrics"] = {}
                posts[idx]["metrics"][window] = metrics
                logger.info(
                    f"メトリクス保存: post_id={post_id}, window={window}, "
                    f"views={metrics.get('views', 0)}, likes={metrics.get('likes', 0)}"
                )

        # API制限を考慮して少し待つ
        if not args.dry_run:
            time.sleep(1)

    # 結果を保存
    posts_data["posts"] = posts
    posts_data["last_fetch_run"] = timestamp_now()

    if not args.dry_run:
        save_json(posts_path, posts_data)
        logger.info(f"投稿データを保存しました: {posts_path}")
    else:
        logger.info("[DRY-RUN] 保存をスキップしました")

    # サマリー
    logger.info(f"=== Fetcher Agent 完了 ===")
    logger.info(f"成功: {success_count}件, エラー: {error_count}件")

    return 0 if error_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
