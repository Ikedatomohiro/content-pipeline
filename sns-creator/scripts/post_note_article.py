#!/usr/bin/env python3
"""
note記事のThreads告知投稿スクリプト

note_queue.jsonからpendingな記事を1件取り出し、
pao.choペルソナに合った告知文を生成してThreadsに投稿する。

使い方:
    python scripts/post_note_article.py
    python scripts/post_note_article.py --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import load_env, setup_logging, timestamp_now, PROJECT_ROOT
from threads_api import ThreadsAPI

logger = setup_logging("post_note_article")

PROFILE_PATH = PROJECT_ROOT / "data" / "pao-pao-cho" / "knowledge" / "profile.json"


def get_queue_path(account: str) -> Path:
    return PROJECT_ROOT / "data" / account / "note_queue.json"


def load_queue(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_queue(path: Path, queue: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def load_profile() -> dict:
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def generate_post_text(title: str, category: str, hashtags: list, description: str, url: str) -> str:
    from openai import OpenAI

    profile = load_profile()
    voice = profile.get("voice", {})
    character = profile.get("character", {})

    system_prompt = f"""あなたは「{character.get("name", "pao.cho")}」というThreadsアカウントのライターです。

キャラクター設定:
- {character.get("persona", "")}
- 一人称: {voice.get("first_person", "僕")}
- 口調: {voice.get("tone", "カジュアルだけど知的")}
- 文体: {voice.get("style", "タメ口ベース、時々です・ます混ぜ")}
- よく使う語彙: {", ".join(voice.get("vocabulary", []))}
- 語尾パターン: {", ".join(voice.get("ending_patterns", []))}
- 絵文字: {voice.get("emoji_usage", "控えめ、0-1個")}

以下のルールを守ってThreads投稿文を1つ生成してください:
- 1行目は強いフックにする（「新記事を書きました」「記事を公開しました」はNG）
- 記事の内容から読者が得られる価値・気づきを伝える
- URLは最後に置く
- ハッシュタグは記事のハッシュタグから1〜2個だけ選ぶ
- 全体で500文字以内
- 投稿文のみ出力すること（説明文や前置きは不要）"""

    user_prompt = f"""以下の記事の告知文を生成してください。

タイトル: {title}
カテゴリ: {category}
概要: {description}
ハッシュタグ候補: {", ".join(hashtags[:6])}
URL: {url}"""

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content.strip()


def parse_args():
    parser = argparse.ArgumentParser(description="note記事キューからThreadsに告知投稿する")
    parser.add_argument("--account", default=os.environ.get("ACTIVE_ACCOUNT", "pao-pao-cho"))
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿しない")
    return parser.parse_args()


def main():
    load_env(required_vars=["THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "OPENAI_API_KEY"])
    args = parse_args()

    queue_path = get_queue_path(args.account)
    queue = load_queue(queue_path)

    pending = [item for item in queue if item.get("status") == "pending"]
    if not pending:
        logger.info("キューにpending記事なし。スキップします。")
        return 0

    # 最も古いpending記事を1件取り出す
    item = sorted(pending, key=lambda x: x.get("queued_at", ""))[0]
    logger.info("告知対象: %s", item["title"])

    post_text = generate_post_text(
        title=item["title"],
        category=item.get("category", ""),
        hashtags=item.get("hashtags", []),
        description=item.get("description", ""),
        url=item["url"],
    )

    logger.info("生成された投稿文:\n%s", post_text)
    logger.info("文字数: %d", len(post_text))

    if args.dry_run:
        logger.info("[DRY-RUN] 投稿をスキップしました")
        return 0

    api = ThreadsAPI()
    result = api.post(post_text)
    logger.info("投稿完了: media_id=%s", result.get("media_id"))

    # キューのステータスを更新
    for q in queue:
        if q["id"] == item["id"]:
            q["status"] = "posted"
            q["posted_at"] = timestamp_now()
            q["threads_media_id"] = result.get("media_id")
            break
    save_queue(queue_path, queue)

    return 0


if __name__ == "__main__":
    sys.exit(main())
