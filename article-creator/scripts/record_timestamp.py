#!/usr/bin/env python3
"""
タイムスタンプ記録ヘルパー。
ディレクターが各フェーズの開始・終了時に1行で呼べるようにする。

使い方:
  python3 scripts/record_timestamp.py <作業ディレクトリ> <フェーズ名> start
  python3 scripts/record_timestamp.py <作業ディレクトリ> <フェーズ名> end
  python3 scripts/record_timestamp.py <作業ディレクトリ> --note "メモ内容"

例:
  python3 scripts/record_timestamp.py outputs/20260329_topic/ brief start
  python3 scripts/record_timestamp.py outputs/20260329_topic/ brief end
  python3 scripts/record_timestamp.py outputs/20260329_topic/ --note "構成チェック1回目でneeds_revision"
"""

import json
import os
import sys
from datetime import datetime


def main():
    if len(sys.argv) < 3:
        print("Usage: record_timestamp.py <dir> <phase> start|end")
        print("       record_timestamp.py <dir> --note \"message\"")
        sys.exit(1)

    work_dir = sys.argv[1]
    path = os.path.join(work_dir, "_timestamps.json")

    # 既存データ読み込み（なければ初期化）
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"phases": {}, "execution_notes": []}

    if "phases" not in data:
        data["phases"] = {}
    if "execution_notes" not in data:
        data["execution_notes"] = []

    now = datetime.now().isoformat()

    if sys.argv[2] == "--note":
        # 実行メモの記録
        note_text = sys.argv[3] if len(sys.argv) > 3 else ""
        data["execution_notes"].append({"time": now, "note": note_text})
        print(f"[timestamp] note recorded: {note_text}")
    else:
        # フェーズの start/end 記録
        phase = sys.argv[2]
        action = sys.argv[3] if len(sys.argv) > 3 else "start"

        if phase not in data["phases"]:
            data["phases"][phase] = {}

        data["phases"][phase][action] = now
        print(f"[timestamp] {phase}.{action} = {now}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
