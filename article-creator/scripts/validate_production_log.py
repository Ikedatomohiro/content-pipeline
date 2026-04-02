#!/usr/bin/env python3
"""
production_log.json のバリデーションスクリプト。
最終統合後にディレクターが実行し、必須フィールドの欠落を検出する。

使い方:
  python3 scripts/validate_production_log.py <作業ディレクトリ>

終了コード:
  0 = OK
  1 = エラーあり（必須フィールド欠落）
"""

import json
import os
import sys


def validate(work_dir: str) -> list[str]:
    """production_log.json を検証し、問題のリストを返す。"""
    errors = []
    path = os.path.join(work_dir, "production_log.json")

    if not os.path.exists(path):
        return ["production_log.json が存在しない"]

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. production_log ラッパーの存在チェック
    if "production_log" not in data:
        errors.append("トップレベルに 'production_log' キーがない（Agent 9 の出力形式と異なる）")
        return errors  # 以降のチェックは不可能

    log = data["production_log"]

    # 2. 必須フィールドのチェック
    required_fields = ["date", "topic", "agents_used", "steps_summary",
                       "fact_check_summary", "total_revisions", "quality_score"]
    for field in required_fields:
        if field not in log:
            errors.append(f"必須フィールド '{field}' がない")

    # 3. steps_summary の中身チェック
    steps = log.get("steps_summary", [])
    if len(steps) < 5:
        errors.append(f"steps_summary が {len(steps)} 件しかない（最低5件必要）")

    # 4. timing セクションのチェック
    timing = log.get("timing")
    if timing is None:
        errors.append("timing セクションがない（_timestamps.json がマージされていない）")
    else:
        phases = timing.get("phases", {})
        null_phases = [k for k, v in phases.items()
                       if v.get("duration_minutes") is None]
        if null_phases:
            errors.append(
                f"timing.phases で duration_minutes が null のフェーズ: {', '.join(null_phases)}"
            )
        if timing.get("total_minutes") is None:
            errors.append("timing.total_minutes が null")

    # 5. lessons_learned チェック
    lessons = log.get("lessons_learned", [])
    if len(lessons) == 0:
        errors.append("lessons_learned が空")

    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_production_log.py <work_dir>")
        sys.exit(1)

    work_dir = sys.argv[1]
    errors = validate(work_dir)

    if errors:
        print(f"❌ production_log.json に {len(errors)} 件の問題:")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}")
        sys.exit(1)
    else:
        print("✅ production_log.json は正しいフォーマットです")
        sys.exit(0)


if __name__ == "__main__":
    main()
