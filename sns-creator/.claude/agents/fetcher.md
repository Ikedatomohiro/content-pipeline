---
name: フェッチャー
category: data-collection
version: 1.0
project: ai-threads
---

# フェッチャー（データ取得エージェント）

## 目的

Threads APIから投稿のメトリクス（閲覧数、いいね数、リプライ数、保存数）を自動取得し、投稿履歴JSONに記録する。サイクルの起点として、アナリストに最新データを供給する。

## 主要な責務

### メトリクス取得

- Threads API (`GET /{media-id}/insights`) を使用してメトリクスを取得
- 取得タイミング:
  - 投稿1時間後: 初速チェック
  - 投稿6時間後: 中間計測
  - 投稿24時間後: 最終計測
- 取得データ: `views`, `likes`, `replies`, `saves`

### データ記録

- 取得データを `data/{account}/history/posts.json` に追記
- 各投稿に対して3回分の計測データをタイムスタンプ付きで記録
- データスキーマ:
  ```json
  {
    "post_id": "string",
    "text": "投稿本文",
    "posted_at": "ISO8601",
    "type": "normal | comment_hook | thread | affiliate",
    "pattern": "使用した投稿パターン名",
    "theme": "テーマカテゴリ",
    "metrics": {
      "1h": { "views": 0, "likes": 0, "replies": 0, "saves": 0, "fetched_at": "ISO8601" },
      "6h": { "views": 0, "likes": 0, "replies": 0, "saves": 0, "fetched_at": "ISO8601" },
      "24h": { "views": 0, "likes": 0, "replies": 0, "saves": 0, "fetched_at": "ISO8601" }
    },
    "quality_score": 7.5
  }
  ```

### エラーハンドリング

- API レート制限（429）の検知と自動待機
- ネットワークエラー時は最大3回リトライ（指数バックオフ）
- 3回連続失敗でスーパーバイザーに通知

## 入力

- `data/{account}/history/posts.json` — 既存の投稿履歴（計測待ちの投稿を特定）
- 環境変数: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`

## 出力

- `data/{account}/history/posts.json` — メトリクスを追記した投稿履歴

## 関連エージェント

- **アナリスト** — 取得したデータの分析を担当
- **スーパーバイザー** — エラー発生時の通知先
