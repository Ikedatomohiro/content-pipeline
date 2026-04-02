#!/usr/bin/env python3
"""デプロイ後のブログURLをblog_urls.jsonに保存する。

使い方: python3 scripts/save_blog_url.py <slug> <blog_url>
"""
import json
import sys

if len(sys.argv) < 3:
    print("Usage: save_blog_url.py <slug> <blog_url>", file=sys.stderr)
    sys.exit(1)

slug = sys.argv[1]
url = sys.argv[2]
path = "blog_urls.json"

try:
    data = json.load(open(path))
except Exception:
    data = {}

data[slug] = url

with open(path, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Saved blog URL: {slug} -> {url}")
