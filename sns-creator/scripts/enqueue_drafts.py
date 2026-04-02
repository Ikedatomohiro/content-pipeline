#!/usr/bin/env python3
"""
Enqueue Agent — 下書きキュー登録

pool.json の下書きを評価し、品質スコア7.0以上のものを queue/pending.json に追加する。
PRマージ時に自動実行される。
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import load_json, save_json, setup_logging, timestamp_now, generate_id, PROJECT_ROOT

MIN_QUALITY_SCORE = 7.0


def parse_args():
    parser = argparse.ArgumentParser(description="Enqueue drafts from pool to pending queue")
    parser.add_argument("--account", "-a", default=os.environ.get("ACTIVE_ACCOUNT", "default"))
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    logger = setup_logging("enqueue", verbose=args.verbose)

    account_path = PROJECT_ROOT / "data" / args.account
    pool_path = account_path / "drafts" / "pool.json"
    queue_path = account_path / "queue" / "pending.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    # pool.json は配列形式
    drafts = load_json(pool_path, default=[])
    if isinstance(drafts, dict):
        drafts = drafts.get("drafts", [])

    # pending.json は {"posts": [...]} 形式
    queue_data = load_json(queue_path, default={"posts": []})
    if isinstance(queue_data, list):
        queue_data = {"posts": queue_data}
    queue = queue_data.setdefault("posts", [])

    existing_draft_ids = {q.get("draft_id") for q in queue}

    added = 0
    for draft in drafts:
        if draft.get("status") != "draft":
            continue

        score = draft.get("quality_score", 0)
        if score < MIN_QUALITY_SCORE:
            logger.info(f"スコア不足でスキップ: {draft.get('draft_id')} (score={score})")
            continue

        draft_id = draft.get("draft_id")
        if draft_id in existing_draft_ids:
            logger.info(f"既にキュー済み: {draft_id}")
            continue

        queue_item = {
            "id": generate_id("queue"),
            "draft_id": draft_id,
            "text": draft.get("text", ""),
            "type": draft.get("type", "normal"),
            "pattern": draft.get("pattern"),
            "theme": draft.get("theme"),
            "comment_text": draft.get("comment_text"),
            "thread_texts": draft.get("thread_texts"),
            "affiliate_comment": draft.get("affiliate_link"),
            "score": score,
            "added_at": timestamp_now(),
            "source": "pool",
        }
        queue.append(queue_item)
        draft["status"] = "queued"
        added += 1
        logger.info(f"キューに追加: {draft_id} (score={score}, pattern={draft.get('pattern')})")

    if added == 0:
        logger.info("新たにキューに追加する下書きはありませんでした")
        return 0

    queue_data["last_updated"] = timestamp_now()
    save_json(queue_path, queue_data)

    # pool.json のステータスを更新
    save_json(pool_path, drafts)

    logger.info(f"=== {added}件をキューに追加しました ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
