# エージェント詳細リファレンス

> ⚠️ 各エージェントの定義は `.claude/agents/` ディレクトリに移動しました。以下の各ファイルを参照してください。

## 現行エージェント（9人チーム）

| ファイル | エージェント |
|------|------|
| `agent-00-director.md` | Agent 0: ディレクター（統括） |
| `agent-01-researcher.md` | Agent 1: リサーチ＆整理担当（調査＋情報整理） |
| `agent-03-structure.md` | Agent 3: 構成担当（設計） |
| `agent-04-structure-checker.md` | Agent 4: 構成チェック担当（確認） |
| `agent-05-writer.md` | Agent 5: 本文執筆担当（執筆） |
| `agent-06-proofreader.md` | Agent 6: 校正担当（校正） |
| `agent-07-factchecker.md` | Agent 7: ファクトチェック担当（2段階検証） |
| `agent-08-designer.md` | Agent 8: デザイン担当（デザイン＋画像提案＋SEO） |
| `agent-10-quality-reviewer.md` | Agent 10: 品質レビュー担当（最終品質チェック） |

## 廃止済み（トークン最適化v2）

| ファイル | 旧エージェント | 移行先 |
|------|------|------|
| `agent-02-summarizer.md` | 旧Agent 2: まとめ担当 | Agent 1に統合（_research.jsonのcontent_strategyセクション） |
| `agent-09-recorder.md` | 旧Agent 9: レコーディング担当 | `scripts/generate_production_log.py` に置換 |
