---
name: blog-writer-multi-agent
description: マルチエージェント・オーケストレーションでブログ記事を作成するスキル。ディレクター（統括）を筆頭に、リサーチ＆整理担当・構成担当・構成チェック担当・本文執筆担当・校正担当・ファクトチェック担当・デザイン担当の約9人のAIチームが協働し、note投稿に最適化された記事を生成する。全員Claudeが動いている。ユーザーが「ブログ記事を書いて」「noteの記事を作って」「記事を作成して」「ブログ書いて」「○○について記事にして」などと言ったとき、またはブログ・note・記事・コンテンツ作成を求めるときは必ずこのスキルを使うこと。
---

# マルチエージェント型ブログ記事作成スキル — AI9人チーム

Claude Code Agent Team を使った約9の専門エージェントがチームとして協働し、質の高いブログ記事を生成する。
ディレクターが全体を統括し、調査・設計・執筆・検証・仕上げの各フェーズを管理する。
最終出力は **note投稿用のMarkdown形式** のテキストファイル。

### トークン最適化（v2）
旧11人チームから以下を最適化し、品質を維持しつつトークン消費を約20-25%削減:
- **Agent 2（まとめ担当）→ Agent 1に統合**: リサーチと情報整理を1エージェントで実行。重複Web検索を解消
- **Agent 9（レコーディング担当）→ Pythonスクリプト化**: `scripts/generate_production_log.py` で機械的に生成
- **Agent 7（ファクトチェック）→ 2段階検証**: 出典URL付きの事実は軽量チェック、出典なしの主張は徹底検証

## アーキテクチャ概要

```
                    ┌─────────────────┐
                    │  ディレクター（統括） │  ← 全体管理・指示出し・品質判定
                    └────────┬────────┘
                             │
                             ▼
                  ┌──────────────────┐
                  │ リサーチ＆整理担当   │  ← 調査+情報整理を1エージェントで
                  │  （調査＋整理）     │
                  └────────┬─────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
   ┌──────────────────┐      ┌──────────────────┐
   │  構成担当（設計）   │◄────►│ 構成チェック担当（確認）│  ← 相互連携
   └────────┬─────────┘      └──────────────────┘
            │
            ▼
   ┌──────────────────┐      ┌──────────────────┐
   │ 本文執筆担当（執筆） │─────►│  校正担当（校正）    │  ← 直列
   └──────────────────┘      └────────┬─────────┘
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
             ┌────────────────┐          ┌────────────────┐
             │ファクトチェック担当│          │ デザイン担当     │  ← 並列実行
             │ （2段階検証）   │          │ （デザイン）     │
             └────────────────┘          └────────────────┘
                        │                           │
                        └─────────────┬─────────────┘
                                      ▼
                           ┌─────────────────────┐
                           │ スクリプト: 制作ログ生成 │  ← Pythonスクリプト
                           └─────────────────────┘
                                      ▼
                             ┌──────────────────┐
                             │  ディレクター最終統合 │
                             └────────┬─────────┘
                                      ▼
                             ┌──────────────────┐
                         ┌──►│ 品質レビュー担当    │◄─┐
                         │   │  （最終品質チェック） │   │  ← 最大3回ループ
                         │   └────────┬─────────┘   │
                         │            ▼              │
                         │   問題あり → 校正担当が修正 ─┘
                         │            ▼
                         │   問題なし（approved）
                         │            ▼
                               最終記事（note投稿用）
```

全員Claudeが動いている。各エージェントはAgent Teamのteammateとして実装する。

## エージェント一覧と実行フロー

**フェーズ0 — 準備**: ペルソナベクトルDB構築（初回・persona更新時のみ）
```bash
# _index.json はpersonaリポ側で管理。ベクトルDBのみローカルで構築する
python3 scripts/build_persona_vectordb.py
```

**フェーズ1 — 企画**: Agent 0 ディレクター（統括）→ ペルソナ検索 + 全体指示書を作成
- ⏱ タイムスタンプ: `total.start` + `brief.start` → 完了後 `brief.end`

**フェーズ2 — 調査＆整理**: Agent 1 リサーチ＆整理担当（旧Agent 1+2を統合）
- ⏱ タイムスタンプ: `research.start` → 完了後 `research.end`

**フェーズ3 — 設計（相互連携）**: Agent 3 構成担当 ⇄ Agent 4 構成チェック担当（最大2回ループ）
- ⏱ タイムスタンプ: `structure.start` → ループ終了後 `structure.end`

**フェーズ4 — 制作（直列）**: Agent 5 本文執筆担当 → Agent 6 校正担当
- ⏱ タイムスタンプ: `writing.start` → 執筆完了 `writing.end` + `proofreading.start` → 校正完了 `proofreading.end`

**フェーズ5 — 仕上げ（並列）**: Agent 7 ファクトチェック（2段階検証）+ Agent 8 デザイン
- ⏱ タイムスタンプ: `finishing.start` → 全完了後 `finishing.end`

**フェーズ5.5 — 制作ログ生成（スクリプト）**: Pythonスクリプトで制作ログを自動生成
```bash
python3 scripts/generate_production_log.py {作業ディレクトリ}
```
- Agent 9 の代わりにスクリプトで `_production_log.json` を生成する（トークン削減）

**フェーズ6 — 統合+品質レビュー（最大3回ループ）**: 最終統合 → Agent 10 品質レビュー担当 ⇄ Agent 6 校正担当
- ⏱ タイムスタンプ: `integration.start` → 統合完了 `integration.end` + `quality_review.start` → ループ終了後 `quality_review.end` + `total.end`
- ⚠️ 統合完了後、`python3 scripts/validate_production_log.py {作業ディレクトリ}` でバリデーションを実行する

ディレクターは各フェーズの開始/終了時に `scripts/record_timestamp.py` を使って `_timestamps.json` にタイムスタンプを記録する（詳細は `agent-00-director.md` の「タイムスタンプ記録手順」参照）。注目すべきイベント（リトライ、ループバック等）は `execution_notes` に記録する。**タイムスタンプの記録漏れは production_log.json の品質に直結するため、絶対に省略しない。**

各エージェントの詳細なシステムプロンプトと仕様は `.claude/agents/` ディレクトリの各ファイルを参照（`agent-00-director.md` 〜 `agent-10-quality-reviewer.md`）。
過去のPRレビューから蓄積されたフィードバックルールは `.claude/rules/article-feedback.md` を参照。全エージェントはこのルールを遵守すること。

## Agent Team 構成指示

### Teammate一覧（8人 + リードの自分 = 9人）

リード（自分）= **Agent 0: ディレクター（統括）**
- 作業ディレクトリ `outputs/YYYYMMDD_タイトル/` を作成（例: `outputs/20260321_2026年税制改正/`）
- ブリーフ（制作方針書）を作成し作業ディレクトリ内の `_brief.json` に保存
- 全体の進行を管理し、最終成果物を統合

**Teammate 1: リサーチ＆整理担当** — Web検索で最新情報を調査し、記事素材として整理（旧Agent 1+2を統合）
**Teammate 3: 構成担当** — 記事の構成を設計
**Teammate 4: 構成チェック担当** — 構成案を読者目線でレビュー
**Teammate 5: 本文執筆担当** — 構成案に沿って記事を執筆
**Teammate 6: 校正担当** — 記事を校正
**Teammate 7: ファクトチェック担当** — 事実関係をWeb検索で2段階検証（出典付き=軽量、出典なし=徹底）
**Teammate 8: デザイン担当** — タイトル最適化・フォーマット・ハッシュタグ・SNS説明文・画像提案(Unsplash)・SEO最適化
**Teammate 10: 品質レビュー担当** — 最終品質チェック（ファクト・URL・面白さ・わかりやすさ）

> **廃止済み**: Teammate 2（まとめ担当）→ Teammate 1に統合、Teammate 9（レコーディング担当）→ `scripts/generate_production_log.py` に置換

### タスク依存関係

```
Task 1: ブリーフ作成         → リード（ブロックなし）
Task 2: リサーチ＆整理       → Teammate 1（blockedBy: Task 1）
Task 3: 構成設計            → Teammate 3（blockedBy: Task 2）
Task 4: 構成チェック         → Teammate 4（blockedBy: Task 3）
  └─ verdict=needs_revision → Task 3に戻る（最大2回ループ、ディレクターが管理）
  └─ verdict=approved → Task 5へ
Task 5: 本文執筆            → Teammate 5（blockedBy: Task 4 approved）
Task 6: 校正               → Teammate 6（blockedBy: Task 5）
Task 7: ファクトチェック      → Teammate 7（blockedBy: Task 6）  ※2段階検証
Task 8: デザイン最適化       → Teammate 8（blockedBy: Task 6）  ※Task 7と並列
Task 9: 制作ログ生成        → リードがスクリプト実行（blockedBy: Task 6）  ※Task 7,8と並列
  python3 scripts/generate_production_log.py {作業ディレクトリ}
Task 10: 最終統合           → リード（blockedBy: Task 7, 8, 9）
Task 11: 品質レビュー       → Teammate 10（blockedBy: Task 10）
  └─ verdict=needs_revision → 以下のサイクルを実行（最大3回ループ、ディレクターが管理）:
     1. Teammate 6 が revision_instructions + issues に基づき article.md を修正
     2. リードが再統合（_proofread.md → article.md に反映）
     3. Task 11 に戻る（Teammate 10 が再レビュー）
  └─ verdict=approved または 3回到達 → PR作成へ
```

### 出力ディレクトリ

記事ごとに `outputs/YYYYMMDD_タイトル/` ディレクトリを作成する。
（例: `outputs/20260321_2026年税制改正/`）

ディレクターが最初にこのディレクトリを作成し、以降すべてのエージェントはこのディレクトリ内にファイルを出力する。

### 中間ファイル（作業ディレクトリ内）

各エージェントは以下のファイルで成果物を受け渡す:

- `_brief.json` — ディレクターのブリーフ
- `_research.json` — リサーチ＆整理結果（旧_summary.jsonの内容もcontent_strategyセクションに統合）
- `_structure.json` — 構成案
- `_structure_review.json` — 構成チェック結果
- `_draft.md` — 記事ドラフト
- `_proofread.md` — 校正済み記事
- `_verified.md` — ファクトチェック済み記事
- `_factcheck.json` — ファクトチェックレポート
- `_design.json` — デザイン最適化結果
- `_production_log.json` — 制作ログ（スクリプトで自動生成）
- `_quality_review.json` — 品質レビュー結果
- `_timestamps.json` — フェーズ別タイムスタンプ（ディレクターが記録）

## 過去記事との重複管理（必須）

記事作成開始前に `published_articles.tsv`（プロジェクトルート直下）を読み、過去の投稿済み記事との関係を把握する。

- ディレクター（Agent 0）がブリーフ作成時に `published_articles.tsv` を読み込む
- **まったく同じ内容の繰り返しはNG**。ただし過去記事を深掘り・発展させる記事はOK
- 過去記事と関連がある場合:
  - `_brief.json` の `risk_points` に「過去記事○○との差別化: ○○」を含める
  - `_brief.json` に `related_past_articles: ["slug1"]` を追加する
  - 執筆担当に「過去記事へのリンクを本文内に含める」よう指示する
- 構成担当・執筆担当は、関連する過去記事がある場合、該当セクションで自然にリンクを挿入する

## 入力パラメータ

- **テーマ / トピック**（必須）
- **ターゲット読者**（任意、デフォルト: 一般読者）
- **トーン**（任意、デフォルト: カジュアルで親しみやすい）
- **文字数目安**（任意、デフォルト: 3000〜5000文字）
- **参考URL・資料**（任意）
- **SEOキーワード**（任意）

## 最終出力

`outputs/YYYYMMDD_タイトル/` ディレクトリ内に以下を出力:

- `article.md` — note投稿用の記事本文（画像情報コメント付き）
- `factcheck.json` — ファクトチェックレポート
- `production_log.json` — 制作ログ（フェーズ別所要時間・実行メモ含む）

中間ファイル（`_`プレフィックス付き）は削除せず、そのまま残す。

## 画像提案（Unsplash連携）

Agent 8（デザイン担当）が記事内容から英語の検索クエリを生成し、`scripts/unsplash_search.sh` 経由でUnsplash APIから画像を検索・提案する。

- アイキャッチ画像: 記事全体のテーマを表す画像1枚（Unsplashから必ず取得）
- 本文挿入画像: 主要セクション向けに1〜3枚（アイキャッチとは異なる画像を使用）

### 環境変数

`UNSPLASH_ACCESS_KEY` を設定すること。設定済みの場合、画像取得をスキップしないこと。

### 画像情報の反映

最終統合時に `article.md` のタイトル直前にアイキャッチ画像をMarkdown画像記法＋クレジットで埋め込む。本文挿入画像は対応するセクション見出しの直後に挿入する。

## エラーハンドリング

- teammate失敗時は最大2回リトライ
- 構成チェック不承認時は最大2回再設計（Task 4→5→4 ループ、ディレクターが verdict を確認して制御）
- 品質レビュー不承認時は最大3回修正（Task 13→校正→再統合→Task 13 ループ、ディレクターが verdict を確認して制御）
- ファイルの読み書きエラー時はリードが介入
