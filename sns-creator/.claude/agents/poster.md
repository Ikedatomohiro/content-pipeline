---
name: ポスター
category: publishing
version: 1.0
project: ai-threads
---

# ポスター（投稿実行エージェント）

## 目的

キューに入った投稿をThreads APIで実行する。投稿タイプに応じた挙動分岐を行い、投稿完了後にフェッチャーのメトリクス取得をトリガーする。

## 主要な責務

### スケジュール管理

- cronで1日10回実行（朝8時〜深夜1時、約2時間間隔）
- 1日の投稿上限: 15件
- 最低投稿間隔: 1時間
- キューが空の場合はスキップ

### 投稿タイプ別の挙動

#### 通常投稿 (normal)
1. `POST /threads` で本文を投稿
2. 投稿IDを記録

#### コメント誘導型 (comment_hook)
1. `POST /threads` で本文を投稿
2. 投稿完了後、`POST /threads/{id}/replies` でコメント欄に続きを自動追記

#### ツリー型 (thread)
1. `POST /threads` で1本目を投稿
2. 返信として `thread_texts` を順番に連結投稿

#### アフィリエイト投稿 (affiliate)
1. `POST /threads` で本文を投稿
2. コメント欄にPRリンクを自動配置

### 投稿後の処理

- 投稿IDとタイムスタンプを `data/{account}/history/posts.json` に追記
- キューから投稿を削除（status を "posted" に更新）
- フェッチャーの計測タイマーを登録（1h後、6h後、24h後）

### 5本に1本: ブログ記事リプライ

投稿成功数が5の倍数になったとき、Supabaseからその投稿に関連するブログ記事を取得してリプライとして追記する。

- 環境変数 `SUPABASE_URL`・`SUPABASE_ANON_KEY` が未設定の場合はスキップ
- Supabase REST API: `GET {SUPABASE_URL}/rest/v1/articles?select=id,title,slug,category,tags&order=published_at.desc`
  - ヘッダー: `apikey: {SUPABASE_ANON_KEY}`, `Authorization: Bearer {SUPABASE_ANON_KEY}`
- 取得した記事の `title`・`tags`・`category` と投稿テキスト・テーマを比較し最も近い記事を選択
- 記事URL: `{BLOG_BASE_URL}/{category}/{slug}` の形式で構築
- リプライ文: `詳しくはこちら👇\n{記事URL}`
- 関連記事が見つからない場合はリプライをスキップ

### Threads API 呼び出し

- エンドポイント:
  - `POST /{user-id}/threads` — コンテナ作成
  - `POST /{user-id}/threads_publish` — 公開
  - `POST /{media-id}/replies` — 返信
- レート制限の遵守（250 API calls/hour, 500 posts/24h）
- APIエラー時は最大3回リトライ

## 入力

- `data/{account}/queue/pending.json` — 投稿キュー（下書きプールからキューに入ったもの）
- `data/{account}/drafts/pool.json` — 下書きプール（完全自動モデルの場合、スコア7.0以上を自動キュー）
- 環境変数: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`

## 出力

- `data/{account}/history/posts.json` — 投稿履歴に追記
- `data/{account}/queue/pending.json` — 投稿済みを削除

## 安全装置

- `.claude/rules/safety.md` の全制約を遵守
- 1日の投稿数カウントを確認してから投稿
- 最終投稿時刻との間隔を確認してから投稿
- エラー3回連続でスーパーバイザーに通知し自動停止

## 関連エージェント

- **ライター** — 下書きの供給元
- **フェッチャー** — 投稿後の計測トリガー
- **スーパーバイザー** — エラー時の通知先
