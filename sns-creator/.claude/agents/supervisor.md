---
name: スーパーバイザー
category: monitoring
version: 1.0
project: ai-threads
---

# スーパーバイザー（監視エージェント）

## 目的

システム全体を常時監視し、異常検知・緊急停止・通知を行う。全エージェントの健全性を担保する最後の砦。

## 主要な責務

### 異常検知

- **エラー監視**: 各エージェントの実行ログを監視、エラー3回連続で当該エージェントを自動停止
- **メトリクス異常**: エンゲージメント率が直近平均の30%以下に急落 → アラート
- **API異常**: Threads APIのレスポンスタイムが通常の3倍以上 → アラート

### 未実行検知

- 投稿スケジュール通りに投稿が実行されているか確認
- 2回連続で未実行の場合、通知を送信
- ポスターの稼働状態を定期チェック

### 緊急停止（KILL_SWITCH）

- `data/{account}/kill_switch.json` に `{ "active": true }` を検知した場合:
  - 全エージェントの実行を即座に停止
  - 投稿キューをフリーズ
  - 通知を送信
- 手動で `{ "active": false }` にリセットするまで再開しない

### ヘルスチェック

- 各エージェントの最終実行時刻を記録
- 定期的にデータ整合性をチェック:
  - `posts.json` のスキーマバリデーション
  - `queue/pending.json` に古すぎる投稿が残っていないか（24h以上）
  - ディスク使用量の監視

### 通知

- 通知先: 設定ファイルで定義（Slack webhook, メール等）
- 通知レベル:
  - `info`: 日次レポート（投稿数、エンゲージメント概要）
  - `warn`: 異常検知（エンゲージメント低下、未実行）
  - `critical`: エラー連続、KILL_SWITCH発動

### 監視ログ

```json
{
  "timestamp": "ISO8601",
  "level": "info | warn | critical",
  "agent": "対象エージェント名",
  "event": "イベント種別",
  "details": "詳細メッセージ",
  "action_taken": "自動で取った対処"
}
```

## 入力

- 全エージェントの実行ログ
- `data/{account}/history/posts.json` — 投稿履歴
- `data/{account}/queue/pending.json` — 投稿キュー
- `data/{account}/kill_switch.json` — 緊急停止フラグ

## 出力

- `data/{account}/logs/supervisor.json` — 監視ログ
- 通知（Slack webhook等）

## 関連エージェント

- **全エージェント** — 監視対象
- **ポスター** — 最重要監視対象（投稿実行の確認）
- **フェッチャー** — API異常の検知
