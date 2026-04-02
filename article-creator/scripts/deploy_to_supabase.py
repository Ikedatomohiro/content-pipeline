#!/usr/bin/env python3
"""記事をSupabaseに直接デプロイする。

環境変数:
  DEPLOY_ARTICLE_PATH: 記事ファイルのパス
  DEPLOY_CATEGORY: カテゴリ (tech/health/asset)
  DEPLOY_SLUG: URLスラッグ
  DEPLOY_TAGS: タグのJSON配列文字列
  SUPABASE_URL: SupabaseプロジェクトURL
  SUPABASE_SERVICE_ROLE_KEY: Supabaseサービスロールキー
  PUBLISH_API_URL: ブログのベースURL（記事URLの生成に使用）

出力: /tmp/deploy_result.json (slug, url)
"""
import json
import os
import sys
import uuid
import urllib.request
from datetime import datetime, timezone

article_path = os.environ["DEPLOY_ARTICLE_PATH"]
category = os.environ["DEPLOY_CATEGORY"]
deploy_slug = os.environ.get("DEPLOY_SLUG", "")
tags_raw = json.loads(os.environ.get("DEPLOY_TAGS", "[]"))
supabase_url = os.environ["SUPABASE_URL"]
supabase_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
site_url = os.environ.get("PUBLISH_API_URL", "https://www.pogo-notes.com")

# タグの # プレフィックスを除去
tags = [t.lstrip("#") for t in tags_raw]

article_dir = os.path.dirname(article_path)
content = open(article_path).read()

# meta.json を読み込み
meta = {}
meta_path = os.path.join(article_dir, "meta.json")
if os.path.exists(meta_path):
    with open(meta_path) as f:
        meta = json.load(f)

# slug: blog_urls.json に既存UUIDがあれば再利用、なければ新規UUID生成
meta_slug = meta.get("slug") or deploy_slug
slug = None
if meta_slug:
    try:
        blog_urls = json.load(open("blog_urls.json"))
        existing_url = blog_urls.get(meta_slug, "")
        if existing_url:
            slug = existing_url.rstrip("/").split("/")[-1]
            print(f"Reusing existing slug for {meta_slug}: {slug}")
    except Exception:
        pass
if not slug:
    slug = str(uuid.uuid4())

# title
title = meta.get("title") or ""
if not title:
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break

# description
description = (
    meta.get("meta_description")
    or meta.get("description")
    or meta.get("sns_description")
    or ""
)

# thumbnail
raw_thumb = meta.get("thumbnail")
if isinstance(raw_thumb, dict):
    thumbnail = raw_thumb.get("url") or raw_thumb.get("photo_url") or ""
else:
    thumbnail = raw_thumb or ""

# tags: meta.json の tags/hashtags を優先
if not tags:
    raw_tags = meta.get("tags") or meta.get("hashtags") or []
    tags = [t.lstrip("#") for t in raw_tags]

# date
raw_date = (
    meta.get("date")
    or meta.get("publish_date")
    or meta.get("created_at")
    or ""
)
if raw_date:
    date = f"{raw_date[:10]}T00:00:00.000Z" if len(raw_date) == 10 else raw_date
else:
    date = datetime.now(timezone.utc).isoformat()

payload = {
    "slug": slug,
    "category": category,
    "title": title,
    "description": description,
    "content": content.strip(),
    "date": date,
    "tags": tags,
    "thumbnail": thumbnail or None,
    "published": True,
}

print(f"Deploying: title={title}, slug={slug}, category={category}")

# Supabase REST API にupsert
endpoint = f"{supabase_url}/rest/v1/articles"
body = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    endpoint,
    data=body,
    method="POST",
    headers={
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    },
)

try:
    with urllib.request.urlopen(req) as res:
        status = res.status
        print(f"✅ Supabase upsert succeeded (HTTP {status}): {slug}")
except urllib.error.HTTPError as e:
    body_err = e.read().decode("utf-8")
    print(f"❌ Supabase upsert failed (HTTP {e.code}): {body_err}", file=sys.stderr)
    sys.exit(1)

article_url = f"{site_url}/{category}/{slug}"
result = {"slug": slug, "url": article_url}
with open("/tmp/deploy_result.json", "w") as f:
    json.dump(result, f)

print(f"Article URL: {article_url}")
