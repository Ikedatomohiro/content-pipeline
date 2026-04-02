#!/usr/bin/env python3
"""
Poster Agent — 投稿エージェント

キュー内の投稿を実際にThreads APIで投稿する。
投稿タイプ（normal/comment_hook/thread/affiliate）に応じた処理を行う。
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# スクリプトディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_json, save_json, setup_logging, timestamp_now, generate_id, PROJECT_ROOT
from threads_api import ThreadsAPI

# 投稿制限
MAX_DAILY_POSTS = 15
MIN_POST_INTERVAL_MINUTES = 60

# 投稿可能時間帯 (JST)
# 8:00 〜 25:00 (= 翌1:00) JST
POSTING_HOURS_START = 8   # JST 8:00
POSTING_HOURS_END = 25    # JST 25:00 (翌日1:00)

# JST オフセット
JST = timezone(timedelta(hours=9))


def parse_args():
    parser = argparse.ArgumentParser(description="Poster Agent: 投稿実行")
    parser.add_argument("--account", "-a", default=os.environ.get("ACTIVE_ACCOUNT", "default"), help="アカウントID")
    parser.add_argument("--dry-run", action="store_true", help="実際の投稿を行わない")
    parser.add_argument("--limit", type=int, default=None, help="投稿数の上限")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    return parser.parse_args()


def is_within_posting_hours() -> bool:
    """現在が投稿可能時間帯内かチェック (8:00-25:00 JST)"""
    now_jst = datetime.now(JST)
    hour = now_jst.hour

    # 25:00 = 翌日1:00
    # 8:00-23:59は通常チェック
    if POSTING_HOURS_START <= hour <= 23:
        return True
    # 0:00-0:59は25時台として扱う（前日の延長）
    if hour == 0:
        return True
    return False


def get_daily_post_count(posts: list) -> int:
    """今日の投稿数を取得 (JST基準)"""
    now_jst = datetime.now(JST)
    today_start = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)

    count = 0
    for post in posts:
        posted_at_str = post.get("posted_at")
        if not posted_at_str:
            continue
        try:
            posted_at = datetime.fromisoformat(posted_at_str)
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            posted_at_jst = posted_at.astimezone(JST)
            if posted_at_jst >= today_start:
                count += 1
        except (ValueError, TypeError):
            continue

    return count


def get_time_since_last_post(posts: list) -> timedelta | None:
    """最後の投稿からの経過時間を取得"""
    now = datetime.now(timezone.utc)

    latest = None
    for post in posts:
        posted_at_str = post.get("posted_at")
        if not posted_at_str:
            continue
        try:
            posted_at = datetime.fromisoformat(posted_at_str)
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            if latest is None or posted_at > latest:
                latest = posted_at
        except (ValueError, TypeError):
            continue

    if latest is None:
        return None

    return now - latest


def check_ng_words(text: str, ng_words: list[str]) -> list[str]:
    """NGワード最終チェック"""
    found = []
    text_lower = text.lower()
    for word in ng_words:
        if word.lower() in text_lower:
            found.append(word)
    return found


def post_normal(api: ThreadsAPI, item: dict, logger, dry_run: bool = False) -> dict | None:
    """通常投稿"""
    text = item.get("text", "")

    if dry_run:
        logger.info(f"[DRY-RUN] 通常投稿: {text[:50]}...")
        return {"threads_post_id": "dry_run_" + generate_id("post"), "type": "normal"}

    try:
        result = api.post(text)
        return {
            "threads_post_id": result.get("media_id"),
            "type": "normal",
        }
    except Exception as e:
        logger.error(f"通常投稿エラー: {e}")
        return None


def post_comment_hook(api: ThreadsAPI, item: dict, logger, dry_run: bool = False) -> dict | None:
    """コメントフック投稿（本文 + 自分コメント）"""
    text = item.get("text", "")
    comment_text = item.get("comment_text", "")

    if dry_run:
        logger.info(f"[DRY-RUN] コメントフック投稿: {text[:50]}...")
        logger.info(f"[DRY-RUN] コメント: {comment_text[:50]}...")
        fake_id = "dry_run_" + generate_id("post")
        return {"threads_post_id": fake_id, "type": "comment_hook", "comment_id": "dry_run_comment"}

    try:
        # メイン投稿
        result = api.post(text)
        post_id = result.get("media_id")

        if not post_id:
            logger.error("投稿IDが取得できませんでした")
            return None

        # 少し待ってからコメント
        time.sleep(3)

        # 自分コメント
        comment_result = api.reply(post_id, comment_text)

        return {
            "threads_post_id": post_id,
            "type": "comment_hook",
            "comment_id": comment_result.get("media_id"),
        }
    except Exception as e:
        logger.error(f"コメントフック投稿エラー: {e}")
        return None


def post_thread(api: ThreadsAPI, item: dict, logger, dry_run: bool = False) -> dict | None:
    """スレッド投稿（複数投稿を連鎖）"""
    text = item.get("text", "")  # 最初の投稿
    thread_texts = item.get("thread_texts", [])

    if dry_run:
        logger.info(f"[DRY-RUN] スレッド投稿: {text[:50]}...")
        for i, tt in enumerate(thread_texts):
            logger.info(f"[DRY-RUN] スレッド{i+2}: {tt[:50]}...")
        fake_id = "dry_run_" + generate_id("post")
        return {
            "threads_post_id": fake_id,
            "type": "thread",
            "thread_ids": [f"dry_run_thread_{i}" for i in range(len(thread_texts))],
        }

    try:
        # 最初の投稿
        result = api.post(text)
        first_post_id = result.get("media_id")

        if not first_post_id:
            logger.error("最初の投稿IDが取得できませんでした")
            return None

        thread_ids = []
        reply_to = first_post_id

        for i, thread_text in enumerate(thread_texts):
            time.sleep(3)  # API制限を考慮
            try:
                reply_result = api.reply(reply_to, thread_text)
                reply_id = reply_result.get("media_id")
                thread_ids.append(reply_id)
                reply_to = reply_id  # 次は直前の投稿にリプライ
                logger.info(f"スレッド{i+2}投稿完了: {reply_id}")
            except Exception as e:
                logger.error(f"スレッド{i+2}の投稿エラー: {e}")
                break

        return {
            "threads_post_id": first_post_id,
            "type": "thread",
            "thread_ids": thread_ids,
        }
    except Exception as e:
        logger.error(f"スレッド投稿エラー: {e}")
        return None


def post_affiliate(api: ThreadsAPI, item: dict, logger, dry_run: bool = False) -> dict | None:
    """アフィリエイト投稿（本文 + アフィリエイトコメント）"""
    text = item.get("text", "")
    affiliate_comment = item.get("affiliate_comment", "")

    if dry_run:
        logger.info(f"[DRY-RUN] アフィリエイト投稿: {text[:50]}...")
        logger.info(f"[DRY-RUN] アフィリエイトコメント: {affiliate_comment[:50]}...")
        fake_id = "dry_run_" + generate_id("post")
        return {"threads_post_id": fake_id, "type": "affiliate", "affiliate_comment_id": "dry_run_aff"}

    try:
        # メイン投稿
        result = api.post(text)
        post_id = result.get("media_id")

        if not post_id:
            logger.error("投稿IDが取得できませんでした")
            return None

        # 少し待ってからアフィリエイトコメント
        time.sleep(5)

        comment_result = api.reply(post_id, affiliate_comment)

        return {
            "threads_post_id": post_id,
            "type": "affiliate",
            "affiliate_comment_id": comment_result.get("media_id"),
        }
    except Exception as e:
        logger.error(f"アフィリエイト投稿エラー: {e}")
        return None


def main():
    args = parse_args()
    logger = setup_logging("poster", verbose=args.verbose)

    logger.info("=== Poster Agent 開始 ===")
    if args.dry_run:
        logger.info("[DRY-RUN モード]")

    # パス設定
    account_path = PROJECT_ROOT / "data" / args.account
    account_path.mkdir(parents=True, exist_ok=True)
    queue_path = account_path / "queue" / "pending.json"
    drafts_path = account_path / "drafts" / "pool.json"
    posts_path = account_path / "history" / "posts.json"
    ng_words_path = account_path / "knowledge" / "ng_words.json"
    config_path = account_path / "config.json"
    supervisor_log_path = account_path / "logs" / "supervisor.json"

    # データ読み込み
    queue_data = load_json(queue_path, default={"posts": []})
    queue = queue_data.get("posts", [])

    drafts_data = load_json(drafts_path, default=[])
    if isinstance(drafts_data, list):
        drafts = drafts_data
    else:
        drafts = drafts_data.get("drafts", [])

    posts_data = load_json(posts_path, default=[])
    if isinstance(posts_data, list):
        posts = posts_data
    else:
        posts = posts_data.get("posts", [])

    ng_words_data = load_json(ng_words_path, default={"words": []})
    ng_words = ng_words_data.get("words", [])

    config = load_json(config_path, default={})
    operation_mode = config.get("operation_mode", "semi_auto")

    # autoモード: スコアの高いドラフトをキューに追加
    if operation_mode == "auto":
        logger.info("自動モード: 高スコアドラフトをキューに追加")
        for draft in drafts:
            if draft.get("status") != "draft":
                continue
            score = draft.get("score", {})
            total_score = score.get("total", 0) if isinstance(score, dict) else 0
            if total_score >= 7.0:
                # キューにすでに同じドラフトがないか確認
                existing_ids = {q.get("draft_id") for q in queue}
                if draft.get("id") not in existing_ids:
                    queue_item = {
                        "id": generate_id("queue"),
                        "draft_id": draft["id"],
                        "text": draft.get("text", ""),
                        "type": draft.get("type", "normal"),
                        "pattern": draft.get("pattern"),
                        "theme": draft.get("theme"),
                        "comment_text": draft.get("comment_text"),
                        "thread_texts": draft.get("thread_texts"),
                        "affiliate_comment": draft.get("affiliate_comment"),
                        "score": total_score,
                        "added_at": timestamp_now(),
                        "source": "auto_queue",
                    }
                    queue.append(queue_item)
                    logger.info(f"キューに追加: draft_id={draft['id']}, score={total_score}")

    if not queue:
        logger.info("投稿キューが空です。終了します。")
        return 0

    logger.info(f"キュー内投稿数: {len(queue)}")

    # 投稿可能時間帯チェック
    if not args.dry_run and not is_within_posting_hours():
        now_jst = datetime.now(JST)
        logger.info(f"投稿可能時間帯外です (現在: JST {now_jst.strftime('%H:%M')})")
        logger.info(f"投稿可能時間: {POSTING_HOURS_START}:00 〜 {POSTING_HOURS_END}:00 JST")
        return 0

    # 今日の投稿数チェック
    daily_count = get_daily_post_count(posts)
    remaining_daily = MAX_DAILY_POSTS - daily_count

    if remaining_daily <= 0 and not args.dry_run:
        logger.info(f"本日の投稿上限に達しています ({daily_count}/{MAX_DAILY_POSTS})")
        return 0

    logger.info(f"本日の投稿数: {daily_count}/{MAX_DAILY_POSTS} (残り: {remaining_daily})")

    # 最後の投稿からの経過時間チェック
    time_since_last = get_time_since_last_post(posts)
    if time_since_last is not None and not args.dry_run:
        minutes_since = time_since_last.total_seconds() / 60
        if minutes_since < MIN_POST_INTERVAL_MINUTES:
            wait_minutes = MIN_POST_INTERVAL_MINUTES - minutes_since
            logger.info(
                f"前回投稿から{minutes_since:.0f}分。"
                f"最低{MIN_POST_INTERVAL_MINUTES}分間隔が必要。"
                f"あと{wait_minutes:.0f}分待ってください。"
            )
            return 0

    # 投稿上限を決定
    post_limit = remaining_daily
    if args.limit is not None:
        post_limit = min(post_limit, args.limit)
    post_limit = min(post_limit, len(queue))

    logger.info(f"投稿予定数: {post_limit}件")

    # API初期化
    api = ThreadsAPI()

    # 投稿実行
    consecutive_errors = 0
    success_count = 0
    error_count = 0
    posted_queue_ids = []

    # ドラフトIDからインデックスへのマッピング
    draft_index = {d.get("id"): i for i, d in enumerate(drafts)}

    for i, item in enumerate(queue[:post_limit]):
        logger.info(f"--- 投稿 {i+1}/{post_limit} ---")

        # NGワード最終チェック
        texts_to_check = [item.get("text", "")]
        if item.get("comment_text"):
            texts_to_check.append(item["comment_text"])
        if item.get("affiliate_comment"):
            texts_to_check.append(item["affiliate_comment"])
        if item.get("thread_texts"):
            texts_to_check.extend(item["thread_texts"])

        ng_found = False
        for text in texts_to_check:
            found = check_ng_words(text, ng_words)
            if found:
                logger.warning(f"NGワード検出（最終チェック）: {found}")
                ng_found = True
                break

        if ng_found:
            logger.warning(f"NGワードのためスキップ: queue_id={item.get('id')}")
            posted_queue_ids.append(item.get("id"))  # キューからは除去
            continue

        # 投稿タイプに応じた処理
        post_type = item.get("type", "normal")
        result = None

        if post_type == "normal":
            result = post_normal(api, item, logger, dry_run=args.dry_run)
        elif post_type == "comment_hook":
            result = post_comment_hook(api, item, logger, dry_run=args.dry_run)
        elif post_type == "thread":
            result = post_thread(api, item, logger, dry_run=args.dry_run)
        elif post_type == "affiliate":
            result = post_affiliate(api, item, logger, dry_run=args.dry_run)
        else:
            logger.warning(f"未知の投稿タイプ: {post_type}")
            result = post_normal(api, item, logger, dry_run=args.dry_run)

        if result is None:
            consecutive_errors += 1
            error_count += 1
            logger.error(f"投稿失敗: queue_id={item.get('id')}, consecutive_errors={consecutive_errors}")

            # 3回連続エラーで停止
            if consecutive_errors >= 3:
                error_msg = f"3回連続投稿エラーにより停止"
                logger.error(error_msg)

                supervisor_log = load_json(supervisor_log_path, default={"errors": [], "warnings": []})
                supervisor_log["errors"].append({
                    "agent": "poster",
                    "message": error_msg,
                    "timestamp": timestamp_now(),
                    "last_queue_id": item.get("id"),
                })
                save_json(supervisor_log_path, supervisor_log)
                break
        else:
            consecutive_errors = 0
            success_count += 1

            # 履歴に追加
            history_entry = {
                "id": generate_id("post"),
                "draft_id": item.get("draft_id"),
                "threads_post_id": result.get("threads_post_id"),
                "text": item.get("text", ""),
                "type": post_type,
                "pattern": item.get("pattern"),
                "theme": item.get("theme"),
                "score": item.get("score"),
                "posted_at": timestamp_now(),
                "status": "posted",
                "post_details": result,
                "metrics": {},
            }
            posts.append(history_entry)

            # キューから除去
            posted_queue_ids.append(item.get("id"))

            # ドラフトステータスを更新
            draft_id = item.get("draft_id")
            if draft_id and draft_id in draft_index:
                idx = draft_index[draft_id]
                drafts[idx]["status"] = "posted"
                drafts[idx]["posted_at"] = timestamp_now()
                drafts[idx]["post_id"] = history_entry["id"]

            logger.info(
                f"投稿成功: threads_id={result.get('threads_post_id')}, "
                f"type={post_type}"
            )

        # API制限を考慮して待つ
        if not args.dry_run and i < post_limit - 1:
            time.sleep(5)

    # 結果を保存
    if not args.dry_run:
        # キューから投稿済みを除去
        queue = [q for q in queue if q.get("id") not in posted_queue_ids]
        queue_data["posts"] = queue
        queue_data["last_run"] = timestamp_now()
        save_json(queue_path, queue_data)

        # 投稿履歴を保存
        if isinstance(posts_data, list):
            save_json(posts_path, posts)
        else:
            posts_data["posts"] = posts
            save_json(posts_path, posts_data)

        # ドラフトステータスを保存
        if isinstance(drafts_data, list):
            save_json(drafts_path, drafts)
        else:
            drafts_data["drafts"] = drafts
            save_json(drafts_path, drafts_data)

        logger.info("データを保存しました")
    else:
        logger.info("[DRY-RUN] 保存をスキップしました")

    # サマリー
    logger.info("=== Poster Agent 完了 ===")
    logger.info(f"成功: {success_count}件, エラー: {error_count}件")
    logger.info(f"キュー残り: {len(queue) - len(posted_queue_ids)}件")

    if consecutive_errors >= 3:
        return 1
    return 0 if error_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
