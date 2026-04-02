#!/usr/bin/env python3
"""
Supervisor Agent — 監視エージェント

システム全体の健全性を監視し、問題を検出・報告する。
キルスイッチ、エラーログ、投稿履歴、データ整合性をチェックする。
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# スクリプトディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_json, save_json, setup_logging, timestamp_now, PROJECT_ROOT

# 設定
ENGAGEMENT_DROP_THRESHOLD = 0.70  # 70%低下で警告
STALE_QUEUE_HOURS = 24            # 24時間以上キューに残っている投稿は問題
RECENT_ERROR_HOURS = 24           # 直近24時間のエラーをチェック


def parse_args():
    parser = argparse.ArgumentParser(description="Supervisor Agent: システム監視")
    parser.add_argument("--account", "-a", default=os.environ.get("ACTIVE_ACCOUNT", "default"), help="アカウントID")
    parser.add_argument("--check-only", action="store_true",
                        help="通知を送らず、レポートのみ出力")
    parser.add_argument("--notify", action="store_true",
                        help="問題検出時に通知を送信")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    parser.add_argument("--dry-run", action="store_true", help="実際の操作を行わない（互換性のため）")
    return parser.parse_args()


class HealthReport:
    """ヘルスレポートを構築するクラス"""

    def __init__(self):
        self.status = "healthy"  # healthy, warning, critical
        self.checks = []
        self.warnings = []
        self.errors = []
        self.info = []

    def add_check(self, name: str, passed: bool, message: str):
        self.checks.append({
            "name": name,
            "passed": passed,
            "message": message,
        })
        if not passed:
            self.warnings.append(f"[{name}] {message}")
            if self.status == "healthy":
                self.status = "warning"

    def add_error(self, name: str, message: str):
        self.errors.append(f"[{name}] {message}")
        self.status = "critical"

    def add_info(self, message: str):
        self.info.append(message)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "timestamp": timestamp_now(),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "info": self.info,
            "summary": {
                "total_checks": len(self.checks),
                "passed": sum(1 for c in self.checks if c["passed"]),
                "failed": sum(1 for c in self.checks if not c["passed"]),
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
        }

    def print_report(self, logger):
        logger.info("=" * 60)
        logger.info("ヘルスレポート")
        logger.info("=" * 60)

        status_icon = {"healthy": "OK", "warning": "WARN", "critical": "CRIT"}
        logger.info(f"ステータス: [{status_icon.get(self.status, '???')}] {self.status.upper()}")
        logger.info("")

        # チェック結果
        for check in self.checks:
            mark = "PASS" if check["passed"] else "FAIL"
            logger.info(f"  [{mark}] {check['name']}: {check['message']}")

        # エラー
        if self.errors:
            logger.info("")
            logger.info("--- エラー ---")
            for error in self.errors:
                logger.error(f"  {error}")

        # 警告
        if self.warnings:
            logger.info("")
            logger.info("--- 警告 ---")
            for warning in self.warnings:
                logger.warning(f"  {warning}")

        # 情報
        if self.info:
            logger.info("")
            logger.info("--- 情報 ---")
            for info in self.info:
                logger.info(f"  {info}")

        logger.info("")
        summary = self.to_dict()["summary"]
        logger.info(
            f"サマリー: {summary['passed']}/{summary['total_checks']} チェック通過, "
            f"エラー: {summary['errors']}, 警告: {summary['warnings']}"
        )
        logger.info("=" * 60)


def check_kill_switch(account_path: Path, report: HealthReport, logger) -> bool:
    """キルスイッチを確認。アクティブならTrue"""
    kill_switch_path = account_path / "kill_switch.json"
    kill_switch = load_json(kill_switch_path, default=None)

    if kill_switch is None:
        report.add_check("キルスイッチ", True, "ファイルなし（正常）")
        return False

    is_active = kill_switch.get("active", False)
    if is_active:
        reason = kill_switch.get("reason", "理由不明")
        activated_at = kill_switch.get("activated_at", "不明")
        report.add_error("キルスイッチ", f"アクティブ！ 理由: {reason}, 発動時刻: {activated_at}")
        logger.critical(f"キルスイッチがアクティブです: {reason}")
        return True

    report.add_check("キルスイッチ", True, "非アクティブ（正常）")
    return False


def check_recent_errors(account_path: Path, report: HealthReport, logger):
    """直近のエラーログを確認"""
    supervisor_log_path = account_path / "logs" / "supervisor.json"
    supervisor_log = load_json(supervisor_log_path, default={"errors": [], "warnings": []})

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=RECENT_ERROR_HOURS)

    recent_errors = []
    for error in supervisor_log.get("errors", []):
        ts_str = error.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                recent_errors.append(error)
        except (ValueError, TypeError):
            recent_errors.append(error)  # パースできないものは含める

    recent_warnings = []
    for warning in supervisor_log.get("warnings", []):
        ts_str = warning.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                recent_warnings.append(warning)
        except (ValueError, TypeError):
            recent_warnings.append(warning)

    if recent_errors:
        report.add_check(
            "エラーログ",
            False,
            f"直近{RECENT_ERROR_HOURS}時間に{len(recent_errors)}件のエラー"
        )
        for err in recent_errors[:5]:  # 最新5件を表示
            report.add_info(f"  エラー: [{err.get('agent', '?')}] {err.get('message', '?')}")
    else:
        report.add_check("エラーログ", True, f"直近{RECENT_ERROR_HOURS}時間にエラーなし")

    if recent_warnings:
        report.add_info(f"直近{RECENT_ERROR_HOURS}時間に{len(recent_warnings)}件の警告あり")


def check_posting_activity(posts: list, report: HealthReport, logger):
    """投稿アクティビティを確認"""
    if not posts:
        report.add_check("投稿アクティビティ", False, "投稿履歴なし")
        return

    # 最新の投稿を取得
    posted = [p for p in posts if p.get("posted_at")]
    if not posted:
        report.add_check("投稿アクティビティ", False, "投稿済みの履歴なし")
        return

    latest = max(posted, key=lambda x: x.get("posted_at", ""))
    latest_at_str = latest.get("posted_at", "")

    try:
        latest_at = datetime.fromisoformat(latest_at_str)
        if latest_at.tzinfo is None:
            latest_at = latest_at.replace(tzinfo=timezone.utc)
        hours_ago = (datetime.now(timezone.utc) - latest_at).total_seconds() / 3600

        if hours_ago > 24:
            report.add_check(
                "投稿アクティビティ",
                False,
                f"最終投稿から{hours_ago:.0f}時間経過（24時間以上）"
            )
        else:
            report.add_check(
                "投稿アクティビティ",
                True,
                f"最終投稿: {hours_ago:.1f}時間前"
            )
    except (ValueError, TypeError):
        report.add_check("投稿アクティビティ", False, f"最終投稿日時のパースエラー: {latest_at_str}")

    # 直近7日間の投稿数
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    weekly_count = 0
    for post in posted:
        try:
            posted_at = datetime.fromisoformat(post.get("posted_at", ""))
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            if posted_at >= week_ago:
                weekly_count += 1
        except (ValueError, TypeError):
            continue

    report.add_info(f"直近7日間の投稿数: {weekly_count}")


def check_engagement_trend(posts: list, report: HealthReport, logger):
    """エンゲージメントトレンドを確認"""
    # 24hメトリクスがある投稿を抽出
    posts_with_metrics = []
    for post in posts:
        metrics = post.get("metrics", {})
        m24 = metrics.get("24h", metrics.get("6h", metrics.get("1h")))
        if m24:
            posts_with_metrics.append((post, m24))

    if len(posts_with_metrics) < 10:
        report.add_info(f"エンゲージメントトレンド: データ不足（{len(posts_with_metrics)}件、最低10件必要）")
        return

    # 直近10件と前の10件を比較
    sorted_posts = sorted(
        posts_with_metrics,
        key=lambda x: x[0].get("posted_at", ""),
    )

    recent = sorted_posts[-10:]
    previous = sorted_posts[-20:-10] if len(sorted_posts) >= 20 else sorted_posts[:len(sorted_posts)-10]

    if not previous:
        report.add_info("エンゲージメントトレンド: 比較データ不足")
        return

    def avg_engagement(items):
        rates = []
        for _, m in items:
            views = m.get("views", 0)
            if views > 0:
                rate = (m.get("likes", 0) + m.get("replies", 0) + m.get("saves", 0)) / views
                rates.append(rate)
        return sum(rates) / len(rates) if rates else 0

    recent_avg = avg_engagement(recent)
    previous_avg = avg_engagement(previous)

    if previous_avg > 0:
        change = (recent_avg - previous_avg) / previous_avg
        if change <= -ENGAGEMENT_DROP_THRESHOLD:
            report.add_check(
                "エンゲージメントトレンド",
                False,
                f"エンゲージメント{abs(change):.0%}低下 "
                f"(前期: {previous_avg:.4f} → 今期: {recent_avg:.4f})"
            )
        elif change < 0:
            report.add_check(
                "エンゲージメントトレンド",
                True,
                f"エンゲージメント{abs(change):.0%}低下（許容範囲内）"
            )
        else:
            report.add_check(
                "エンゲージメントトレンド",
                True,
                f"エンゲージメント{change:.0%}上昇"
            )
    else:
        report.add_info("エンゲージメントトレンド: 前期データなし")


def check_json_integrity(account_path: Path, report: HealthReport, logger):
    """全JSONファイルの整合性チェック"""
    json_files = [
        "history/posts.json",
        "drafts/pool.json",
        "queue/pending.json",
        "analysis/latest.json",
        "research/ideas.json",
        "knowledge/strategy.json",
        "knowledge/profile.json",
        "knowledge/ng_words.json",
        "config.json",
        "logs/supervisor.json",
    ]

    broken_files = []
    missing_files = []

    for rel_path in json_files:
        full_path = account_path / rel_path
        if not full_path.exists():
            missing_files.append(rel_path)
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            broken_files.append(f"{rel_path}: {e}")
        except Exception as e:
            broken_files.append(f"{rel_path}: {e}")

    if broken_files:
        report.add_error(
            "JSON整合性",
            f"{len(broken_files)}件のJSONファイルが破損: {', '.join(broken_files)}"
        )
    else:
        report.add_check("JSON整合性", True, "全JSONファイルが正常にパース可能")

    if missing_files:
        report.add_info(f"未作成のJSONファイル: {', '.join(missing_files)}")


def check_stale_queue(account_path: Path, report: HealthReport, logger):
    """古いキューアイテムをチェック"""
    queue_path = account_path / "queue" / "pending.json"
    queue_data = load_json(queue_path, default={"posts": []})
    queue = queue_data.get("posts", [])

    if not queue:
        report.add_check("キュー鮮度", True, "キューは空")
        return

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=STALE_QUEUE_HOURS)
    stale_items = []

    for item in queue:
        added_at_str = item.get("added_at", item.get("created_at", ""))
        try:
            added_at = datetime.fromisoformat(added_at_str)
            if added_at.tzinfo is None:
                added_at = added_at.replace(tzinfo=timezone.utc)
            if added_at < cutoff:
                stale_items.append(item.get("id", "不明"))
        except (ValueError, TypeError):
            continue

    if stale_items:
        report.add_check(
            "キュー鮮度",
            False,
            f"{len(stale_items)}件のキューアイテムが{STALE_QUEUE_HOURS}時間以上滞留"
        )
    else:
        report.add_check("キュー鮮度", True, f"全{len(queue)}件が{STALE_QUEUE_HOURS}時間以内")


def check_orphaned_drafts(account_path: Path, report: HealthReport, logger):
    """孤立したドラフトIDをチェック"""
    drafts_path = account_path / "drafts" / "pool.json"
    posts_path = account_path / "history" / "posts.json"
    queue_path = account_path / "queue" / "pending.json"

    drafts_data = load_json(drafts_path, default={"drafts": []})
    drafts = drafts_data.get("drafts", [])

    posts_data = load_json(posts_path, default={"posts": []})
    posts = posts_data.get("posts", [])

    queue_data = load_json(queue_path, default={"posts": []})
    queue = queue_data.get("posts", [])

    # postedステータスのドラフトで、投稿履歴に対応するIDがないもの
    posted_draft_ids = {p.get("draft_id") for p in posts if p.get("draft_id")}
    queued_draft_ids = {q.get("draft_id") for q in queue if q.get("draft_id")}

    orphaned = []
    for draft in drafts:
        if draft.get("status") == "posted":
            if draft.get("id") not in posted_draft_ids:
                orphaned.append(draft.get("id", "不明"))

    if orphaned:
        report.add_check(
            "ドラフト整合性",
            False,
            f"{len(orphaned)}件の孤立ドラフトID（posted状態だが履歴に未登録）"
        )
    else:
        report.add_check("ドラフト整合性", True, "孤立ドラフトなし")

    report.add_info(f"ドラフト総数: {len(drafts)}, 投稿済み: {len(posted_draft_ids)}, キュー内: {len(queued_draft_ids)}")


def main():
    args = parse_args()
    logger = setup_logging("supervisor", verbose=args.verbose)

    logger.info("=== Supervisor Agent 開始 ===")

    # パス設定
    account_path = PROJECT_ROOT / "data" / args.account
    account_path.mkdir(parents=True, exist_ok=True)
    supervisor_log_path = account_path / "logs" / "supervisor.json"

    # ヘルスレポート初期化
    report = HealthReport()

    # 1. キルスイッチチェック
    kill_active = check_kill_switch(account_path, report, logger)
    if kill_active:
        report.print_report(logger)
        # キルスイッチがアクティブな場合は即座に終了
        save_report_to_log(report, supervisor_log_path)
        return 1

    # 2. エラーログチェック
    check_recent_errors(account_path, report, logger)

    # 3. 投稿アクティビティチェック
    posts_data = load_json(account_path / "history" / "posts.json", default={"posts": []})
    posts = posts_data.get("posts", [])

    check_posting_activity(posts, report, logger)

    # 4. エンゲージメントトレンドチェック
    check_engagement_trend(posts, report, logger)

    # 5. データ整合性チェック
    check_json_integrity(account_path, report, logger)

    # 6. キュー鮮度チェック
    check_stale_queue(account_path, report, logger)

    # 7. 孤立ドラフトチェック
    check_orphaned_drafts(account_path, report, logger)

    # レポート出力
    report.print_report(logger)

    # ログに保存
    save_report_to_log(report, supervisor_log_path)

    # 通知（--notifyフラグ時）
    if args.notify and not args.check_only:
        if report.status in ("warning", "critical"):
            send_notification(report, logger)

    # 終了コード
    if report.status == "critical":
        return 1
    elif report.status == "warning":
        return 2
    return 0


def save_report_to_log(report: HealthReport, supervisor_log_path: Path):
    """レポートをスーパーバイザーログに保存"""
    supervisor_log = load_json(supervisor_log_path, default={"errors": [], "warnings": [], "reports": []})

    if "reports" not in supervisor_log:
        supervisor_log["reports"] = []

    # レポートを追加（最新10件を保持）
    supervisor_log["reports"].append(report.to_dict())
    supervisor_log["reports"] = supervisor_log["reports"][-10:]

    # レポートからのエラー・警告をログにも追加
    for error in report.errors:
        supervisor_log["errors"].append({
            "agent": "supervisor",
            "message": error,
            "timestamp": timestamp_now(),
        })

    for warning in report.warnings:
        supervisor_log["warnings"].append({
            "agent": "supervisor",
            "message": warning,
            "timestamp": timestamp_now(),
        })

    save_json(supervisor_log_path, supervisor_log)


def send_notification(report: HealthReport, logger):
    """
    通知を送信する（プレースホルダー）

    NOTE: 実際の通知はSlack Webhook, LINE Notify, Discord Webhook等で実装
    TODO: 通知チャンネルの設定をconfig.jsonに追加
    """
    logger.info("--- 通知送信 ---")
    logger.info(f"ステータス: {report.status}")

    if report.errors:
        logger.info(f"エラー数: {len(report.errors)}")
        for error in report.errors[:3]:
            logger.info(f"  - {error}")

    if report.warnings:
        logger.info(f"警告数: {len(report.warnings)}")
        for warning in report.warnings[:3]:
            logger.info(f"  - {warning}")

    # TODO: 実際の通知実装
    # - Slack Webhook
    # - LINE Notify
    # - Discord Webhook
    # - メール通知
    logger.info("[通知] プレースホルダー: 実際の通知チャンネルは未実装")


if __name__ == "__main__":
    sys.exit(main())
