# Content Pipeline

ブログ記事とSNS投稿を生成・管理する自動化パイプライン。

## 構成

```
content-pipeline/       ← このリポジトリ（パブリック）
├── article-creator/    ← ブログ記事生成 (Claude Code エージェントチーム)
├── sns-creator/        ← SNS投稿生成・投稿 (Python + Claude Code)
├── external/
│   ├── persona/        ← ペルソナ知識（プライベートサブモジュール）
│   └── content-data/   ← 生成データ保存（プライベートサブモジュール）
└── .github/workflows/
    ├── article-creator.yml   ← @claude で記事生成
    ├── sns-creator.yml       ← 毎朝7時: リサーチャー+ライター
    ├── sns-poster.yml        ← 10/13/18時: Threads投稿
    ├── sns-cycle.yml         ← フェッチャー+アナリスト (手動)
    └── receive-article.yml   ← 記事公開 → SNSキュー追加
```

## content-data 構造

```
external/content-data/
├── sns/
│   └── {account}/    ← ACTIVE_ACCOUNT で指定
│       ├── drafts/pool.json
│       ├── queue/pending.json
│       ├── history/posts.json
│       ├── research/ideas.json
│       ├── analysis/latest.json
│       ├── note_queue.json
│       └── kill_switch.json
└── articles/
    └── outputs/      ← 生成記事
```

## データパス

SNSスクリプトは `DATA_ROOT` 環境変数でデータディレクトリを切り替えます。
- ローカル: `sns-creator/data/`（デフォルト）
- CI: `$GITHUB_WORKSPACE/external/content-data/sns`

## 必要なシークレット

| シークレット | 用途 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code Action |
| `PERSONA_PAT` | persona サブモジュール取得 |
| `CONTENT_DATA_PAT` | content-data サブモジュール取得・push |
| `THREADS_ACCESS_TOKEN` | Threads API |
| `THREADS_USER_ID` | Threads ユーザーID |
| `ACTIVE_ACCOUNT` | アクティブアカウント名 (`pao-pao-cho`) |
| `OPERATION_MODE` | `auto` or `semi_auto` |
| `UNSPLASH_ACCESS_KEY` | 記事用画像 (article-creator) |
| `SOCIALDATA_API_KEY` | SNS調査 (researcher) |
