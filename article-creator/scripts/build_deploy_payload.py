#!/usr/bin/env python3
"""記事デプロイ用のJSONペイロードを生成する。

環境変数:
  DEPLOY_ARTICLE_PATH: 記事ファイルのパス
  DEPLOY_CATEGORY: カテゴリ (tech/health/asset)
  DEPLOY_SLUG: URLスラッグ
  DEPLOY_TAGS: タグのJSON配列文字列

出力: /tmp/deploy_payload.json
"""
import json
import os
import uuid
from datetime import datetime, timezone

article_path = os.environ["DEPLOY_ARTICLE_PATH"]
category = os.environ["DEPLOY_CATEGORY"]
deploy_slug = os.environ.get("DEPLOY_SLUG", "")
tags = json.loads(os.environ.get("DEPLOY_TAGS", "[]"))

# blog_urls.json に既存UUIDがあれば再利用（同じURLに上書きデプロイ）
slug = None
if deploy_slug:
    try:
        blog_urls = json.load(open("blog_urls.json"))
        existing_url = blog_urls.get(deploy_slug, "")
        if existing_url:
            slug = existing_url.rstrip("/").split("/")[-1]
            print(f"Reusing existing slug for {deploy_slug}: {slug}")
    except Exception:
        pass
if not slug:
    slug = str(uuid.uuid4())

content = open(article_path).read()
article_dir = os.path.dirname(article_path)

# meta.json を先に読み込み（タイトル・サムネイル・日付の信頼できるソース）
thumbnail = None
created_at = None
meta_title = None
meta_path = os.path.join(article_dir, "meta.json")
if os.path.exists(meta_path):
    with open(meta_path) as f:
        meta = json.load(f)
    meta_title = meta.get("title")
    raw_thumbnail = meta.get("thumbnail")
    # thumbnail がオブジェクトの場合はURLを抽出する
    if isinstance(raw_thumbnail, dict):
        thumbnail = raw_thumbnail.get("url") or raw_thumbnail.get("photo_url")
    else:
        thumbnail = raw_thumbnail
    created_at = meta.get("created_at") or meta.get("publish_date") or meta.get("published_date")

# タイトル: meta.json を優先、なければ本文の最初の # 見出し、それもなければ先頭行
title = None
if meta_title:
    title = meta_title
if not title:
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break
if not title:
    # # 見出しがない場合、先頭の空でない行をタイトルとして使う
    for line in content.split("\n"):
        line = line.strip()
        if line:
            title = line
            break
if not title:
    title = slug

if not thumbnail:
    from urllib.parse import quote
    site_url = os.environ.get("PUBLISH_API_URL", "https://writing-taupe.vercel.app")
    thumbnail = f"{site_url}/api/og?title={quote(title)}&category={quote(category)}"

# デプロイ日時: meta.json の created_at があればISO 8601に変換、なければ現在時刻
if created_at:
    # "2026-03-28" → "2026-03-28T00:00:00Z" に変換
    if len(created_at) == 10:
        published_at = f"{created_at}T00:00:00Z"
    else:
        published_at = created_at
else:
    published_at = datetime.now(timezone.utc).isoformat()

payload = {
    "title": title,
    "content": content,
    "category": category,
    "slug": slug,
    "tags": tags,
    "thumbnail": thumbnail,
    "published": True,
    "publishedAt": published_at,
}

with open("/tmp/deploy_payload.json", "w") as f:
    json.dump(payload, f, ensure_ascii=False)

print(f"Payload built: title={title}, category={category}, slug={slug}, thumbnail={'yes' if thumbnail else 'no'}, publishedAt={published_at}")
