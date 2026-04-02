---
name: browser-use
description: Browser Use CLIを使ってブラウザを操作するスキル。Chromeプロファイルを使ってログイン済みの状態でWebページの閲覧・操作・スクリーンショット・データ抽出などを行う。「ブラウザで開いて」「Webページを見て」「スクリーンショット撮って」「ブラウザ操作して」などと言われたときに使う。
---

# Browser Use CLI スキル

Browser Use CLI を使ってChromeブラウザを操作し、Webページの閲覧・操作を行う。

## セットアップ

Browser Use CLI は `/Users/tomo/.browser-use-env/` にインストール済み。

## 使い方

すべてのコマンドは以下のプレフィックスを付けて実行すること：

```bash
export PATH="/Users/tomo/.browser-use/bin:$PATH" && source /Users/tomo/.browser-use-env/bin/activate && browser-use --profile Default --headed <command>
```

`--profile Default` フラグにより、ログイン済みのChromeプロファイルを使用する。
これによりGoogle、SNS等の認証済みサービスにそのままアクセスできる。
別ターミナルでのChrome起動や `--remote-debugging-port` の設定は不要。

## 主要コマンド

### ナビゲーション
- `browser-use --profile Default --headed open <url>` — URLを開く
- `browser-use --profile Default --headed back` — 戻る
- `browser-use --profile Default --headed scroll up|down` — スクロール

### 状態取得
- `browser-use --profile Default --headed state` — ページの要素一覧を取得（クリック可能な要素のインデックス付き）
- `browser-use --profile Default --headed screenshot <path>` — スクリーンショットを保存
- `browser-use --profile Default --headed get url` — 現在のURLを取得
- `browser-use --profile Default --headed get title` — ページタイトルを取得

### 操作
- `browser-use --profile Default --headed click <index>` — 要素をクリック（indexはstateで確認）
- `browser-use --profile Default --headed type "text"` — テキスト入力
- `browser-use --profile Default --headed input <index> "text"` — 特定要素にテキスト入力
- `browser-use --profile Default --headed select <index> "value"` — ドロップダウン選択
- `browser-use --profile Default --headed keys "Enter"` — キー送信
- `browser-use --profile Default --headed hover <index>` — ホバー

### タブ管理
- `browser-use --profile Default --headed switch <tab_index>` — タブ切り替え
- `browser-use --profile Default --headed close-tab` — タブを閉じる

### データ抽出
- `browser-use --profile Default --headed extract "抽出したい情報の説明"` — LLMを使ったデータ抽出
- `browser-use --profile Default --headed eval "document.title"` — JavaScript実行

### セッション管理
- `browser-use sessions` — アクティブセッション一覧
- `browser-use close` — ブラウザを閉じてデーモン停止

## 実行フロー

1. `--profile Default --headed` でChromeプロファイルを使ってブラウザをGUI表示で起動・接続
2. `open <url>` でページを開く
3. `state` でページ構造を確認
4. 必要に応じて `click`、`input`、`scroll` 等で操作
5. `screenshot` で結果を視覚確認（`/tmp/` に保存し Read ツールで表示）
6. 作業完了後、必要に応じて `close` でセッション終了

## 注意事項

- スクリーンショットは `/tmp/` に保存し、Read ツールで表示する
- `state` の出力に含まれる `[index]` 番号を使って要素を操作する
- タイムアウトは適切に設定すること（ページ読み込みに時間がかかる場合がある）
- Google Sheetsなどの複雑なWebアプリでは `eval` でのDOM取得が難しい場合がある。その場合はスクリーンショットで内容を確認する
