#!/usr/bin/env python3
"""ai-threadsリポジトリにdispatchイベントを送信する。

環境変数:
  ARTICLE_TITLE: 記事タイトル
  ARTICLE_CATEGORY: カテゴリ
  ARTICLE_HASHTAGS: ハッシュタグ（カンマ区切り）
  ARTICLE_DESC: 記事説明
  ARTICLE_URL: 記事URL
  AI_THREADS_PAT: GitHub Personal Access Token
"""
import json
import os
import sys
import urllib.request

payload = json.dumps({
    "event_type": "note-article-published",
    "client_payload": {
        "title": os.environ.get("ARTICLE_TITLE", ""),
        "category": os.environ.get("ARTICLE_CATEGORY", ""),
        "hashtags": os.environ.get("ARTICLE_HASHTAGS", ""),
        "description": os.environ.get("ARTICLE_DESC", ""),
        "url": os.environ.get("ARTICLE_URL", ""),
    },
}).encode("utf-8")

token = os.environ.get("AI_THREADS_PAT", "")
req = urllib.request.Request(
    "https://api.github.com/repos/Ikedatomohiro/ai-threads/dispatches",
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    },
)

try:
    with urllib.request.urlopen(req) as res:
        print(f"✅ Notified ai-threads (HTTP {res.status})")
except urllib.error.HTTPError as e:
    print(f"⚠️ Failed to notify ai-threads (HTTP {e.code}): {e.read().decode()}", file=sys.stderr)
    sys.exit(1)
