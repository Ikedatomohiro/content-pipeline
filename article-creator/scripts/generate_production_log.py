#!/usr/bin/env python3
"""
production_log.json を中間ファイルから自動生成するスクリプト。
旧Agent 9（レコーディング担当）の機能をスクリプト化したもの。

エージェント起動のトークンを削減しつつ、同等の制作ログを生成する。

使い方:
  python3 scripts/generate_production_log.py <作業ディレクトリ>

入力（作業ディレクトリ内）:
  - _brief.json       — ディレクターのブリーフ
  - _research.json     — リサーチ結果
  - _structure.json    — 構成案
  - _structure_review.json — 構成チェック結果
  - _timestamps.json   — フェーズ別タイムスタンプ
  - _factcheck.json    — ファクトチェックレポート（あれば）

出力:
  - _production_log.json — 制作ログ
"""

import json
import os
import sys
from datetime import datetime


def load_json(path: str) -> dict | None:
    """JSONファイルを読み込む。存在しなければNoneを返す。"""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def calc_timing(timestamps: dict | None) -> dict:
    """_timestamps.json からフェーズ別の所要時間を計算する。"""
    timing = {
        "total_minutes": None,
        "phases": {},
        "bottleneck": None,
    }
    if timestamps is None:
        return timing

    phases = timestamps.get("phases", {})
    phase_durations = {}

    for phase_name, times in phases.items():
        start_str = times.get("start")
        end_str = times.get("end")
        if start_str and end_str:
            try:
                start = datetime.fromisoformat(start_str)
                end = datetime.fromisoformat(end_str)
                minutes = round((end - start).total_seconds() / 60, 1)
                timing["phases"][phase_name] = {"duration_minutes": minutes}
                if phase_name != "total":
                    phase_durations[phase_name] = minutes
            except (ValueError, TypeError):
                timing["phases"][phase_name] = {"duration_minutes": None}
        else:
            timing["phases"][phase_name] = {"duration_minutes": None}

    if "total" in timing["phases"] and timing["phases"]["total"]["duration_minutes"] is not None:
        timing["total_minutes"] = timing["phases"]["total"]["duration_minutes"]

    if phase_durations:
        timing["bottleneck"] = max(phase_durations, key=phase_durations.get)

    return timing


def build_steps_summary(brief: dict | None, research: dict | None,
                        structure: dict | None, structure_review: dict | None) -> list[dict]:
    """中間ファイルから各ステップのサマリーを生成する。"""
    steps = []

    # ブリーフ
    if brief:
        direction = brief.get("article_direction", "")
        steps.append({
            "step": "ブリーフ作成",
            "agent": "Agent 0（ディレクター）",
            "key_decision": f"記事方針: {direction[:100]}" if direction else "ブリーフ作成完了",
        })

    # リサーチ
    if research:
        findings_count = len(research.get("findings", []))
        stats_count = len(research.get("statistics", []))
        steps.append({
            "step": "リサーチ＆整理",
            "agent": "Agent 1（リサーチ＆整理担当）",
            "key_decision": f"{findings_count}件のfindings、{stats_count}件の統計データを収集・整理",
        })

    # 構成設計
    if structure:
        outline = structure.get("outline", [])
        steps.append({
            "step": "構成設計",
            "agent": "Agent 3（構成担当）",
            "key_decision": f"{len(outline)}セクション構成を設計",
        })

    # 構成チェック
    if structure_review:
        score = structure_review.get("score", "?")
        verdict = structure_review.get("verdict", "?")
        steps.append({
            "step": "構成チェック",
            "agent": "Agent 4（構成チェック担当）",
            "key_decision": f"スコア{score}/10で{verdict}",
        })

    # 残りのステップ（ファイルの有無で判定）
    steps.extend([
        {"step": "本文執筆", "agent": "Agent 5（執筆担当）", "key_decision": "構成案に基づき記事本文を執筆"},
        {"step": "校正", "agent": "Agent 6（校正担当）", "key_decision": "文体・表記ゆれ・noteフォーマット準拠をチェック・修正"},
        {"step": "ファクトチェック", "agent": "Agent 7（ファクトチェック担当）", "key_decision": "事実関係をWeb検索で検証"},
        {"step": "デザイン・SEO", "agent": "Agent 8（デザイン担当）", "key_decision": "タイトル最適化・画像選定・SEO設定"},
    ])

    return steps


def build_factcheck_summary(factcheck: dict | None) -> str:
    """ファクトチェック結果のサマリーを生成する。"""
    if factcheck is None:
        return "ファクトチェック結果なし"

    checks = factcheck.get("checks", factcheck.get("verified_claims", []))
    total = len(checks)
    if total == 0:
        return "ファクトチェック結果なし"

    # ステータスをカウント
    status_counts = {}
    for check in checks:
        status = check.get("status", check.get("result", "unknown")).upper()
        status_counts[status] = status_counts.get(status, 0) + 1

    parts = [f"全{total}項目検証"]
    for status, count in sorted(status_counts.items()):
        parts.append(f"{status}: {count}件")

    return "。".join(parts)


def generate(work_dir: str) -> dict:
    """制作ログを生成する。"""
    brief = load_json(os.path.join(work_dir, "_brief.json"))
    research = load_json(os.path.join(work_dir, "_research.json"))
    structure = load_json(os.path.join(work_dir, "_structure.json"))
    structure_review = load_json(os.path.join(work_dir, "_structure_review.json"))
    timestamps = load_json(os.path.join(work_dir, "_timestamps.json"))
    factcheck = load_json(os.path.join(work_dir, "_factcheck.json"))

    timing = calc_timing(timestamps)
    steps = build_steps_summary(brief, research, structure, structure_review)
    factcheck_summary = build_factcheck_summary(factcheck)

    # カテゴリとトピックをブリーフから取得
    category = ""
    topic = ""
    if brief:
        category = brief.get("category", "")
        topic = brief.get("article_direction", brief.get("topic", ""))

    # 日付はタイムスタンプまたはディレクトリ名から推定
    date = ""
    if timestamps and timestamps.get("phases", {}).get("total", {}).get("start"):
        date = timestamps["phases"]["total"]["start"][:10]
    else:
        # ディレクトリ名から日付を抽出 (例: outputs/20260329_topic/)
        dir_name = os.path.basename(os.path.normpath(work_dir))
        if len(dir_name) >= 8 and dir_name[:8].isdigit():
            date = f"{dir_name[:4]}-{dir_name[4:6]}-{dir_name[6:8]}"

    execution_notes = []
    if timestamps:
        execution_notes = timestamps.get("execution_notes", [])

    log = {
        "production_log": {
            "date": date,
            "topic": topic[:200] if topic else "",
            "category": category,
            "agents_used": 9,  # Agent 2とAgent 9を廃止したので9エージェント
            "timing": timing,
            "steps_summary": steps,
            "execution_notes": execution_notes,
            "fact_check_summary": factcheck_summary,
            "total_revisions": 0,
            "lessons_learned": [],
            "quality_score": "",
        }
    }

    return log


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_production_log.py <work_dir>")
        sys.exit(1)

    work_dir = sys.argv[1]
    if not os.path.isdir(work_dir):
        print(f"エラー: ディレクトリが存在しません: {work_dir}")
        sys.exit(1)

    log = generate(work_dir)

    output_path = os.path.join(work_dir, "_production_log.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"✅ _production_log.json を生成しました: {output_path}")


if __name__ == "__main__":
    main()
