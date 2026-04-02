#!/usr/bin/env python3
"""
Analyst Agent — 分析エージェント

過去の投稿データからエンゲージメント分析を行い、
Writer向けの改善指示を生成する。
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# スクリプトディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_json, save_json, setup_logging, timestamp_now, PROJECT_ROOT


def parse_args():
    parser = argparse.ArgumentParser(description="Analyst Agent: エンゲージメント分析")
    parser.add_argument("--account", "-a", default=os.environ.get("ACTIVE_ACCOUNT", "default"), help="アカウントID")
    parser.add_argument("--min-posts", type=int, default=10, help="分析に必要な最小投稿数")
    parser.add_argument("--dry-run", action="store_true", help="ファイルに保存しない")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    return parser.parse_args()


def get_24h_metrics(post: dict) -> dict | None:
    """24hメトリクスを取得。なければ最新のウィンドウを使う"""
    metrics = post.get("metrics", {})
    # 優先順位: 24h > 6h > 1h
    for window in ["24h", "6h", "1h"]:
        if window in metrics:
            return metrics[window]
    return None


def calculate_engagement_rate(metrics: dict) -> float:
    """エンゲージメント率を計算: (likes + replies + saves) / views"""
    views = metrics.get("views", 0)
    if views == 0:
        return 0.0
    engagement = (
        metrics.get("likes", 0)
        + metrics.get("replies", 0)
        + metrics.get("saves", 0)
    )
    return engagement / views


def analyze_by_pattern(posts_with_metrics: list) -> dict:
    """パターン別エンゲージメント分析"""
    pattern_stats = defaultdict(lambda: {"total_rate": 0.0, "count": 0, "posts": []})

    for post, metrics, rate in posts_with_metrics:
        pattern = post.get("pattern", "unknown")
        pattern_stats[pattern]["total_rate"] += rate
        pattern_stats[pattern]["count"] += 1
        pattern_stats[pattern]["posts"].append({
            "id": post.get("id"),
            "rate": round(rate, 4),
        })

    result = {}
    for pattern, stats in pattern_stats.items():
        avg_rate = stats["total_rate"] / stats["count"] if stats["count"] > 0 else 0
        result[pattern] = {
            "avg_engagement_rate": round(avg_rate, 4),
            "post_count": stats["count"],
            "top_post": max(stats["posts"], key=lambda x: x["rate"]) if stats["posts"] else None,
        }

    return result


def analyze_by_theme(posts_with_metrics: list) -> dict:
    """テーマ別エンゲージメント分析"""
    theme_stats = defaultdict(lambda: {"total_rate": 0.0, "count": 0})

    for post, metrics, rate in posts_with_metrics:
        theme = post.get("theme", "unknown")
        theme_stats[theme]["total_rate"] += rate
        theme_stats[theme]["count"] += 1

    result = {}
    for theme, stats in theme_stats.items():
        avg_rate = stats["total_rate"] / stats["count"] if stats["count"] > 0 else 0
        result[theme] = {
            "avg_engagement_rate": round(avg_rate, 4),
            "post_count": stats["count"],
        }

    return result


def analyze_by_hour(posts_with_metrics: list) -> dict:
    """時間帯別エンゲージメント分析"""
    hour_stats = defaultdict(lambda: {"total_rate": 0.0, "count": 0})

    for post, metrics, rate in posts_with_metrics:
        posted_at_str = post.get("posted_at", "")
        try:
            posted_at = datetime.fromisoformat(posted_at_str)
            hour = posted_at.hour
            hour_stats[hour]["total_rate"] += rate
            hour_stats[hour]["count"] += 1
        except (ValueError, TypeError):
            continue

    result = {}
    for hour, stats in hour_stats.items():
        avg_rate = stats["total_rate"] / stats["count"] if stats["count"] > 0 else 0
        result[str(hour)] = {
            "avg_engagement_rate": round(avg_rate, 4),
            "post_count": stats["count"],
        }

    return result


def identify_top_and_weak_patterns(pattern_analysis: dict) -> tuple[list, list]:
    """トップパターンとウィークパターンを特定"""
    if not pattern_analysis:
        return [], []

    rates = [p["avg_engagement_rate"] for p in pattern_analysis.values()]
    avg_rate = sum(rates) / len(rates) if rates else 0

    top_patterns = []
    weak_patterns = []

    for pattern, stats in pattern_analysis.items():
        rate = stats["avg_engagement_rate"]
        if rate >= avg_rate * 1.5:
            top_patterns.append({
                "pattern": pattern,
                "avg_engagement_rate": rate,
                "multiplier": round(rate / avg_rate, 2) if avg_rate > 0 else 0,
            })
        elif rate <= avg_rate * 0.5:
            weak_patterns.append({
                "pattern": pattern,
                "avg_engagement_rate": rate,
                "multiplier": round(rate / avg_rate, 2) if avg_rate > 0 else 0,
            })

    # エンゲージメント率の降順でソート
    top_patterns.sort(key=lambda x: x["avg_engagement_rate"], reverse=True)
    weak_patterns.sort(key=lambda x: x["avg_engagement_rate"])

    return top_patterns, weak_patterns


def find_best_posting_hours(hour_analysis: dict, top_n: int = 5) -> list:
    """最適な投稿時間を特定"""
    sorted_hours = sorted(
        hour_analysis.items(),
        key=lambda x: x[1]["avg_engagement_rate"],
        reverse=True,
    )
    return [
        {"hour": int(hour), "avg_engagement_rate": stats["avg_engagement_rate"], "post_count": stats["post_count"]}
        for hour, stats in sorted_hours[:top_n]
        if stats["post_count"] >= 2  # 最低2件以上のデータがある時間帯のみ
    ]


def generate_writer_instructions(
    top_patterns: list,
    weak_patterns: list,
    best_hours: list,
    theme_analysis: dict,
    overall_avg: float,
) -> dict:
    """Writer向け指示JSONを生成"""
    instructions = {
        "generated_at": timestamp_now(),
        "overall_avg_engagement_rate": round(overall_avg, 4),
        "preferred_patterns": [p["pattern"] for p in top_patterns],
        "avoid_patterns": [p["pattern"] for p in weak_patterns],
        "best_posting_hours": [h["hour"] for h in best_hours],
        "theme_priorities": [],
        "guidelines": [],
    }

    # テーマ優先度（エンゲージメント率でソート）
    sorted_themes = sorted(
        theme_analysis.items(),
        key=lambda x: x[1]["avg_engagement_rate"],
        reverse=True,
    )
    instructions["theme_priorities"] = [
        {"theme": theme, "avg_engagement_rate": stats["avg_engagement_rate"]}
        for theme, stats in sorted_themes
    ]

    # ガイドライン生成
    if top_patterns:
        instructions["guidelines"].append(
            f"高パフォーマンスパターンを優先: {', '.join(p['pattern'] for p in top_patterns[:3])}"
        )
    if weak_patterns:
        instructions["guidelines"].append(
            f"低パフォーマンスパターンを控える: {', '.join(p['pattern'] for p in weak_patterns[:3])}"
        )
    if best_hours:
        hours_str = ", ".join(f"{h['hour']}時" for h in best_hours[:3])
        instructions["guidelines"].append(f"最適投稿時間: {hours_str}")

    return instructions


def check_engagement_drop(current_avg: float, analysis_path: Path, logger) -> bool:
    """前回の分析と比較してエンゲージメントが70%以上低下しているかチェック"""
    previous = load_json(analysis_path, default=None)
    if previous is None:
        return False

    prev_avg = previous.get("overall_avg_engagement_rate", 0)
    if prev_avg == 0:
        return False

    drop_rate = (prev_avg - current_avg) / prev_avg
    if drop_rate >= 0.7:
        logger.warning(
            f"エンゲージメント大幅低下検出: "
            f"前回={prev_avg:.4f} → 今回={current_avg:.4f} "
            f"(低下率: {drop_rate:.1%})"
        )
        return True

    return False


def main():
    args = parse_args()
    logger = setup_logging("analyst", verbose=args.verbose)

    logger.info("=== Analyst Agent 開始 ===")

    # パス設定
    account_path = PROJECT_ROOT / "data" / args.account
    account_path.mkdir(parents=True, exist_ok=True)
    posts_path = account_path / "history" / "posts.json"
    analysis_path = account_path / "analysis" / "latest.json"
    supervisor_log_path = account_path / "logs" / "supervisor.json"

    # 投稿データ読み込み
    posts_data = load_json(posts_path, default={"posts": []})
    all_posts = posts_data.get("posts", [])

    # 24hメトリクスがある投稿を抽出（最新30件）
    posts_with_24h = []
    for post in all_posts:
        metrics = get_24h_metrics(post)
        if metrics:
            posts_with_24h.append((post, metrics))

    # 最新30件に制限
    posts_with_24h = posts_with_24h[-30:]

    if len(posts_with_24h) < args.min_posts:
        logger.warning(
            f"分析に必要なデータ不足: {len(posts_with_24h)}件 < {args.min_posts}件（最低必要数）"
        )
        # データ不足でも部分的な分析は行う
        if len(posts_with_24h) == 0:
            logger.info("分析可能なデータがありません。終了します。")
            return 0

    logger.info(f"分析対象: {len(posts_with_24h)}件の投稿")

    # エンゲージメント率を計算
    posts_with_metrics = []
    for post, metrics in posts_with_24h:
        rate = calculate_engagement_rate(metrics)
        posts_with_metrics.append((post, metrics, rate))

    # 全体平均
    all_rates = [rate for _, _, rate in posts_with_metrics]
    overall_avg = sum(all_rates) / len(all_rates) if all_rates else 0
    logger.info(f"全体平均エンゲージメント率: {overall_avg:.4f}")

    # パターン別分析
    pattern_analysis = analyze_by_pattern(posts_with_metrics)
    logger.info(f"パターン分析完了: {len(pattern_analysis)}パターン")

    # テーマ別分析
    theme_analysis = analyze_by_theme(posts_with_metrics)
    logger.info(f"テーマ分析完了: {len(theme_analysis)}テーマ")

    # 時間帯別分析
    hour_analysis = analyze_by_hour(posts_with_metrics)
    logger.info(f"時間帯分析完了: {len(hour_analysis)}時間帯")

    # トップ/ウィークパターン
    top_patterns, weak_patterns = identify_top_and_weak_patterns(pattern_analysis)
    logger.info(f"トップパターン: {len(top_patterns)}件, ウィークパターン: {len(weak_patterns)}件")

    # 最適投稿時間
    best_hours = find_best_posting_hours(hour_analysis)
    logger.info(f"最適投稿時間: {len(best_hours)}件")

    # エンゲージメント低下チェック
    engagement_dropped = check_engagement_drop(overall_avg, analysis_path, logger)
    if engagement_dropped:
        supervisor_log = load_json(supervisor_log_path, default={"errors": [], "warnings": []})
        supervisor_log["warnings"].append({
            "agent": "analyst",
            "message": "エンゲージメント率が前回比70%以上低下",
            "timestamp": timestamp_now(),
            "current_avg": round(overall_avg, 4),
        })
        save_json(supervisor_log_path, supervisor_log)

    # Writer向け指示を生成
    writer_instructions = generate_writer_instructions(
        top_patterns, weak_patterns, best_hours, theme_analysis, overall_avg
    )

    # 分析結果を構築
    analysis_result = {
        "generated_at": timestamp_now(),
        "post_count": len(posts_with_metrics),
        "overall_avg_engagement_rate": round(overall_avg, 4),
        "pattern_analysis": pattern_analysis,
        "theme_analysis": theme_analysis,
        "hour_analysis": hour_analysis,
        "top_patterns": top_patterns,
        "weak_patterns": weak_patterns,
        "best_posting_hours": best_hours,
        "writer_instructions": writer_instructions,
        "engagement_drop_detected": engagement_dropped,
    }

    # 保存
    if not args.dry_run:
        save_json(analysis_path, analysis_result)
        logger.info(f"分析結果を保存しました: {analysis_path}")
    else:
        logger.info("[DRY-RUN] 保存をスキップしました")

    # サマリー出力
    logger.info("=== 分析サマリー ===")
    logger.info(f"  分析対象投稿数: {len(posts_with_metrics)}")
    logger.info(f"  全体平均エンゲージメント率: {overall_avg:.4f}")
    if top_patterns:
        logger.info(f"  トップパターン: {', '.join(p['pattern'] for p in top_patterns)}")
    if weak_patterns:
        logger.info(f"  ウィークパターン: {', '.join(p['pattern'] for p in weak_patterns)}")
    if best_hours:
        logger.info(f"  最適投稿時間: {', '.join(str(h['hour']) + '時' for h in best_hours)}")
    logger.info("=== Analyst Agent 完了 ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
