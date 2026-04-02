#!/usr/bin/env python3
"""
Researcher Agent — リサーチエージェント

テーマツリーに基づいてコンテンツアイデアのギャップを分析し、
リサーチが必要なテーマを特定する。

NOTE: 実際のウェブスクレイピング・API連携はClaude Codeエージェントが
このスクリプトの出力を元に実行する。このスクリプトはギャップ分析と
リサーチ計画の生成を担当する。
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

# スクリプトディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_json, save_json, setup_logging, timestamp_now, generate_id, PROJECT_ROOT

# テーマごとに最低限必要な未使用アイデア数
MIN_IDEAS_PER_THEME = 3

# リサーチソースの定義（プレースホルダー）
RESEARCH_SOURCES = {
    "youtube": {
        "name": "YouTube",
        "enabled": False,  # TODO: YouTube Data API連携
        "description": "YouTubeトレンド動画・コメントからアイデアを収集",
    },
    "x_twitter": {
        "name": "X (Twitter)",
        "enabled": False,  # TODO: X API連携
        "description": "Xのトレンド・バズツイートからアイデアを収集",
    },
    "instagram": {
        "name": "Instagram",
        "enabled": False,  # TODO: Instagram Graph API連携
        "description": "Instagramリール・ストーリーからトレンドを分析",
    },
    "threads": {
        "name": "Threads",
        "enabled": False,  # TODO: Threads API検索連携
        "description": "Threadsの人気投稿からアイデアを収集",
    },
    "news": {
        "name": "ニュースサイト",
        "enabled": False,  # TODO: ニュースAPI連携
        "description": "最新ニュースからタイムリーなアイデアを生成",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Researcher Agent: アイデアギャップ分析")
    parser.add_argument("--account", "-a", default=os.environ.get("ACTIVE_ACCOUNT", "default"), help="アカウントID")
    parser.add_argument("--min-ideas", type=int, default=MIN_IDEAS_PER_THEME,
                        help=f"テーマあたり最低アイデア数（デフォルト: {MIN_IDEAS_PER_THEME}）")
    parser.add_argument("--dry-run", action="store_true", help="ファイルに保存しない")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    return parser.parse_args()


def extract_themes_from_strategy(strategy: dict) -> list[dict]:
    """戦略JSONからテーマツリーを抽出する"""
    themes = []
    theme_tree = strategy.get("theme_tree", strategy.get("themes", []))

    if isinstance(theme_tree, dict):
        # テーマツリーが辞書形式の場合
        for category, sub_themes in theme_tree.items():
            if isinstance(sub_themes, list):
                for theme in sub_themes:
                    if isinstance(theme, str):
                        themes.append({
                            "category": category,
                            "theme": theme,
                            "full_path": f"{category}/{theme}",
                        })
                    elif isinstance(theme, dict):
                        theme_name = theme.get("name", theme.get("theme", ""))
                        themes.append({
                            "category": category,
                            "theme": theme_name,
                            "full_path": f"{category}/{theme_name}",
                            "keywords": theme.get("keywords", []),
                            "priority": theme.get("priority", "normal"),
                        })
            elif isinstance(sub_themes, str):
                themes.append({
                    "category": category,
                    "theme": sub_themes,
                    "full_path": f"{category}/{sub_themes}",
                })
    elif isinstance(theme_tree, list):
        # テーマツリーがリスト形式の場合
        for item in theme_tree:
            if isinstance(item, str):
                themes.append({
                    "category": "general",
                    "theme": item,
                    "full_path": item,
                })
            elif isinstance(item, dict):
                category = item.get("category", "general")
                sub_themes = item.get("themes", item.get("sub_themes", []))
                if isinstance(sub_themes, list):
                    for st in sub_themes:
                        if isinstance(st, str):
                            themes.append({
                                "category": category,
                                "theme": st,
                                "full_path": f"{category}/{st}",
                            })
                        elif isinstance(st, dict):
                            st_name = st.get("name", st.get("theme", ""))
                            themes.append({
                                "category": category,
                                "theme": st_name,
                                "full_path": f"{category}/{st_name}",
                                "keywords": st.get("keywords", []),
                                "priority": st.get("priority", "normal"),
                            })
                else:
                    theme_name = item.get("name", item.get("theme", ""))
                    if theme_name:
                        themes.append({
                            "category": category,
                            "theme": theme_name,
                            "full_path": f"{category}/{theme_name}",
                        })

    return themes


def count_ideas_per_theme(ideas: list) -> dict:
    """テーマごとの未使用アイデア数をカウント"""
    counts = defaultdict(lambda: {"total": 0, "unused": 0, "used": 0})

    for idea in ideas:
        theme = idea.get("theme", "unknown")
        counts[theme]["total"] += 1
        if idea.get("used", False):
            counts[theme]["used"] += 1
        else:
            counts[theme]["unused"] += 1

    return dict(counts)


def identify_gaps(themes: list, idea_counts: dict, min_ideas: int) -> list[dict]:
    """アイデアが不足しているテーマを特定"""
    gaps = []

    for theme_info in themes:
        theme = theme_info.get("theme", "")
        full_path = theme_info.get("full_path", theme)

        # テーマ名またはフルパスでカウントを検索
        counts = idea_counts.get(theme, idea_counts.get(full_path, {"total": 0, "unused": 0, "used": 0}))
        unused = counts["unused"]

        if unused < min_ideas:
            gap = {
                "theme": theme,
                "full_path": full_path,
                "category": theme_info.get("category", "general"),
                "current_unused": unused,
                "current_total": counts["total"],
                "needed": min_ideas - unused,
                "priority": theme_info.get("priority", "normal"),
                "keywords": theme_info.get("keywords", []),
            }
            gaps.append(gap)

    # 優先度とギャップの大きさでソート
    priority_order = {"high": 0, "normal": 1, "low": 2}
    gaps.sort(key=lambda x: (priority_order.get(x["priority"], 1), -x["needed"]))

    return gaps


def generate_research_plan(gaps: list, logger) -> list[dict]:
    """リサーチ計画を生成する"""
    plan = []

    for gap in gaps:
        research_item = {
            "id": generate_id("research"),
            "theme": gap["theme"],
            "full_path": gap["full_path"],
            "category": gap["category"],
            "ideas_needed": gap["needed"],
            "priority": gap["priority"],
            "keywords": gap["keywords"],
            "status": "pending",
            "created_at": timestamp_now(),
            "suggested_sources": [],
            # TODO: 実際のリサーチソース提案ロジック
            "research_prompts": [
                f"「{gap['theme']}」に関するThreadsで反響が得られそうなアイデアを{gap['needed']}個生成",
                f"「{gap['theme']}」のトレンドトピックを調査",
                f"「{gap['theme']}」で人気のある投稿パターンを分析",
            ],
        }

        # 利用可能なソースを提案
        for source_id, source_info in RESEARCH_SOURCES.items():
            if source_info["enabled"]:
                research_item["suggested_sources"].append({
                    "source": source_id,
                    "name": source_info["name"],
                    "query_suggestions": gap.get("keywords", [gap["theme"]]),
                })

        plan.append(research_item)
        logger.info(
            f"リサーチ計画: {gap['full_path']} — "
            f"不足={gap['needed']}件, 優先度={gap['priority']}"
        )

    return plan


def main():
    args = parse_args()
    logger = setup_logging("researcher", verbose=args.verbose)

    logger.info("=== Researcher Agent 開始 ===")

    # パス設定
    account_path = PROJECT_ROOT / "data" / args.account
    account_path.mkdir(parents=True, exist_ok=True)
    strategy_path = account_path / "knowledge" / "strategy.json"
    ideas_path = account_path / "research" / "ideas.json"
    research_needed_path = account_path / "research" / "_research_needed.json"

    # 戦略読み込み
    strategy = load_json(strategy_path, default=None)
    if strategy is None:
        logger.error(f"戦略ファイルが見つかりません: {strategy_path}")
        logger.error("knowledge/strategy.json にテーマツリーを定義してください")
        return 1

    # テーマツリー抽出
    themes = extract_themes_from_strategy(strategy)
    if not themes:
        logger.error("テーマツリーが空です。strategy.jsonを確認してください。")
        return 1

    logger.info(f"テーマ数: {len(themes)}")

    # 既存アイデア読み込み
    ideas_data = load_json(ideas_path, default={"ideas": []})
    ideas = ideas_data.get("ideas", [])
    logger.info(f"既存アイデア数: {len(ideas)}")

    # テーマごとのアイデア数カウント
    idea_counts = count_ideas_per_theme(ideas)

    # ギャップ分析
    gaps = identify_gaps(themes, idea_counts, args.min_ideas)

    if not gaps:
        logger.info("すべてのテーマに十分なアイデアがあります。リサーチ不要。")
        # 空のリサーチ計画を保存
        save_json(research_needed_path, {
            "generated_at": timestamp_now(),
            "status": "no_gaps",
            "gaps": [],
            "research_plan": [],
        })
        return 0

    logger.info(f"アイデア不足テーマ: {len(gaps)}件")

    # リサーチ計画生成
    research_plan = generate_research_plan(gaps, logger)

    # リサーチ計画を保存
    research_needed = {
        "generated_at": timestamp_now(),
        "status": "research_needed",
        "total_gaps": len(gaps),
        "total_ideas_needed": sum(g["needed"] for g in gaps),
        "gaps": gaps,
        "research_plan": research_plan,
        "available_sources": {
            source_id: {
                "name": info["name"],
                "enabled": info["enabled"],
                "description": info["description"],
            }
            for source_id, info in RESEARCH_SOURCES.items()
        },
        # TODO: YouTube Data API でトレンド動画を取得
        # TODO: X API でバズツイートを検索
        # TODO: Instagram Graph API でリールトレンドを分析
        # TODO: ニュースAPIで最新トピックを取得
        "notes": [
            "このファイルはClaude Codeエージェントが実際のリサーチを行うための入力として使用される",
            "research_plan内の各アイテムに対してClaude Codeがアイデアを生成し、ideas.jsonに追加する",
            "APIソースは現在未実装。手動リサーチまたはClaude Codeによる生成が主な方法",
        ],
    }

    save_json(research_needed_path, research_needed)
    logger.info(f"リサーチ計画を保存しました: {research_needed_path}")

    # サマリー出力
    logger.info("=== リサーチギャップサマリー ===")
    for gap in gaps:
        logger.info(
            f"  [{gap['priority'].upper()}] {gap['full_path']}: "
            f"未使用={gap['current_unused']}, 必要={gap['needed']}件追加"
        )
    logger.info(f"  合計不足アイデア数: {sum(g['needed'] for g in gaps)}")
    logger.info("=== Researcher Agent 完了 ===")

    # ギャップがある場合はwarning exitコード
    return 2 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
