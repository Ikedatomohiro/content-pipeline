#!/usr/bin/env python3
"""
note記事をキューに追加するスクリプト

note-creatorのdeploy-article.ymlからrepository_dispatch経由で呼ばれる。
受け取った記事情報をnote_queue.jsonに積む。

使い方:
    python scripts/queue_note_article.py \
        --title "記事タイトル" \
        --category tech \
        --hashtags "AI,プログラミング" \
        --description "記事の概要" \
        --url "https://writing-taupe.vercel.app/tech/uuid"
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, timestamp_now, generate_id, PROJECT_ROOT

logger = setup_logging("queue_note_article")


def get_queue_path(account: str) -> Path:
    path = PROJECT_ROOT / "data" / account / "note_queue.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_queue(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_queue(path: Path, queue: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def parse_args():
    parser = argparse.ArgumentParser(description="note記事をキューに追加する")
    parser.add_argument("--title", required=True)
    parser.add_argument("--category", default="")
    parser.add_argument("--hashtags", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--url", required=True)
    parser.add_argument("--account", default=os.environ.get("ACTIVE_ACCOUNT", "pao-pao-cho"))
    return parser.parse_args()


def main():
    args = parse_args()

    queue_path = get_queue_path(args.account)
    queue = load_queue(queue_path)

    # 同じURLが既にキューにあればスキップ
    existing_urls = {item["url"] for item in queue}
    if args.url in existing_urls:
        logger.info("既にキュー済み: %s", args.url)
        return 0

    item = {
        "id": generate_id(),
        "title": args.title,
        "category": args.category,
        "hashtags": [h.strip() for h in args.hashtags.split(",") if h.strip()],
        "description": args.description,
        "url": args.url,
        "queued_at": timestamp_now(),
        "status": "pending",
    }
    queue.append(item)
    save_queue(queue_path, queue)

    logger.info("キューに追加: %s", args.title)
    logger.info("キュー残数: %d件", len(queue))
    return 0


if __name__ == "__main__":
    sys.exit(main())
