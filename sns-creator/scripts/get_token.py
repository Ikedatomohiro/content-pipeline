#!/usr/bin/env python3
"""
Threads APIアクセストークン取得ツール

OAuth認証フローでアクセストークンを取得する。
グラフAPIエクスプローラを使わずにトークンを取得できる。

使い方:
  1. Meta開発者ダッシュボードでリダイレクトURIを設定
     → https://localhost:8000/callback
  2. このスクリプトを実行
     → python get_token.py --app-id YOUR_APP_ID --app-secret YOUR_APP_SECRET
  3. ブラウザで表示されるURLを開いて認証
  4. トークンが表示される → .envに貼り付け
"""

import argparse
import http.server
import json
import ssl
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import os
import tempfile


# === SSL証明書の自動生成 ===
def generate_self_signed_cert():
    """ローカル用の自己署名証明書を生成"""
    cert_dir = tempfile.mkdtemp()
    cert_file = os.path.join(cert_dir, "cert.pem")
    key_file = os.path.join(cert_dir, "key.pem")

    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", key_file, "-out", cert_file,
        "-days", "1", "-nodes",
        "-subj", "/CN=localhost"
    ], capture_output=True, check=True)

    return cert_file, key_file


# === 認証コードを受け取るローカルサーバー ===
class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "✅ 認証成功！ターミナルに戻ってください。このタブは閉じてOKです。"
                .encode("utf-8")
            )
        elif "error" in params:
            error_msg = params.get("error_message", params.get("error", ["不明なエラー"]))[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"❌ エラー: {error_msg}".encode("utf-8")
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # ログを抑制


def exchange_code_for_token(app_id, app_secret, code, redirect_uri):
    """認証コードをアクセストークンに交換"""
    url = "https://graph.threads.net/oauth/access_token"
    data = urllib.parse.urlencode({
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"\n❌ トークン交換エラー: {e.code}")
        print(f"   {error_body}")
        return None


def exchange_for_long_lived_token(app_secret, short_token):
    """短期トークンを長期トークン（60日）に交換"""
    url = "https://graph.threads.net/access_token"
    params = urllib.parse.urlencode({
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    })

    req = urllib.request.Request(f"{url}?{params}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"\n⚠️  長期トークン交換エラー: {e.code}")
        print(f"   {error_body}")
        return None


def get_user_profile(access_token):
    """ユーザープロフィールを取得"""
    url = "https://graph.threads.net/v1.0/me"
    params = urllib.parse.urlencode({
        "fields": "id,username,name,threads_profile_picture_url",
        "access_token": access_token,
    })

    req = urllib.request.Request(f"{url}?{params}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"\n⚠️  プロフィール取得エラー: {e.code}")
        print(f"   {error_body}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Threads APIアクセストークン取得ツール")
    parser.add_argument("--app-id", required=True, help="ThreadsアプリID")
    parser.add_argument("--app-secret", required=True, help="Threadsアプリシークレット")
    parser.add_argument("--port", type=int, default=8000, help="コールバックサーバーのポート（デフォルト: 8000）")
    args = parser.parse_args()

    redirect_uri = f"https://localhost:{args.port}/callback"

    # スコープ（必要な権限）
    scopes = [
        "threads_basic",
        "threads_content_publish",
        "threads_manage_insights",
        "threads_manage_replies",
    ]

    # 認証URL生成
    auth_url = (
        f"https://threads.net/oauth/authorize"
        f"?client_id={args.app_id}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&scope={','.join(scopes)}"
        f"&response_type=code"
    )

    print("=" * 60)
    print("  Threads API アクセストークン取得ツール")
    print("=" * 60)
    print()

    # SSL証明書を生成
    print("🔐 SSL証明書を生成中...")
    try:
        cert_file, key_file = generate_self_signed_cert()
    except Exception as e:
        print(f"❌ SSL証明書の生成に失敗: {e}")
        print()
        print("代わりにHTTPで試みます。")
        print("Meta開発者ダッシュボードのリダイレクトURIを")
        print(f"  http://localhost:{args.port}/callback")
        print("に変更してください。")
        cert_file = None
        key_file = None
        redirect_uri = f"http://localhost:{args.port}/callback"

        # 認証URLを再生成
        auth_url = (
            f"https://threads.net/oauth/authorize"
            f"?client_id={args.app_id}"
            f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
            f"&scope={','.join(scopes)}"
            f"&response_type=code"
        )

    # ローカルサーバー起動
    server = http.server.HTTPServer(("localhost", args.port), OAuthCallbackHandler)
    if cert_file and key_file:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_file, key_file)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        protocol = "HTTPS"
    else:
        protocol = "HTTP"

    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print(f"✅ コールバックサーバー起動 ({protocol} localhost:{args.port})")
    print()
    print("📋 以下のURLをブラウザで開いてください:")
    print()
    print(f"  {auth_url}")
    print()
    print("⏳ 認証を待っています...")

    # 認証コードを待つ
    server_thread.join(timeout=300)  # 5分タイムアウト

    if not OAuthCallbackHandler.auth_code:
        print("\n❌ タイムアウト: 5分以内に認証が完了しませんでした")
        sys.exit(1)

    code = OAuthCallbackHandler.auth_code
    print(f"\n✅ 認証コード取得成功")

    # 短期トークンを取得
    print("\n🔄 アクセストークンに交換中...")
    token_data = exchange_code_for_token(args.app_id, args.app_secret, code, redirect_uri)

    if not token_data or "access_token" not in token_data:
        print("❌ トークン取得に失敗しました")
        sys.exit(1)

    short_token = token_data["access_token"]
    user_id = token_data.get("user_id", "不明")
    print(f"✅ 短期アクセストークン取得成功")
    print(f"   ユーザーID: {user_id}")

    # 長期トークンに交換
    print("\n🔄 長期トークン（60日）に交換中...")
    long_token_data = exchange_for_long_lived_token(args.app_secret, short_token)

    if long_token_data and "access_token" in long_token_data:
        access_token = long_token_data["access_token"]
        expires_in = long_token_data.get("expires_in", "不明")
        print(f"✅ 長期トークン取得成功（有効期限: {expires_in}秒 ≒ 60日）")
    else:
        access_token = short_token
        print("⚠️  長期トークンへの交換に失敗。短期トークンを使用します")

    # プロフィール確認
    print("\n👤 プロフィール確認中...")
    profile = get_user_profile(access_token)
    if profile:
        print(f"   ID: {profile.get('id')}")
        print(f"   ユーザー名: @{profile.get('username', '不明')}")
        print(f"   名前: {profile.get('name', '不明')}")

    # 結果表示
    print()
    print("=" * 60)
    print("  .env に以下を設定してください")
    print("=" * 60)
    print()
    print(f"THREADS_ACCESS_TOKEN={access_token}")
    print(f"THREADS_USER_ID={user_id}")
    print()

    # .envファイルに書き込むか確認
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        print(f"⚠️  {env_path} は既に存在します。手動で上記の値を貼り付けてください。")
    else:
        print(f"💾 {env_path} に自動保存しますか？ (y/n): ", end="")
        answer = input().strip().lower()
        if answer == "y":
            with open(env_path, "w") as f:
                f.write(f"THREADS_ACCESS_TOKEN={access_token}\n")
                f.write(f"THREADS_USER_ID={user_id}\n")
                f.write(f"ACTIVE_ACCOUNT=\n")
                f.write(f"OPERATION_MODE=human_check\n")
            print(f"✅ {env_path} に保存しました")
            print("   ACTIVE_ACCOUNT を手動で設定してください")
        else:
            print("   手動で .env を作成してください")

    print()
    print("🎉 完了！")


if __name__ == "__main__":
    main()
