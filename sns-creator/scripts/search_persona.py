#!/usr/bin/env python3
"""
ペルソナナレッジの統合検索ツール。

2つの検索モードを提供し、結果をマージしてランキングする:
  1. キーワード検索 — インデックスのタグ・テキストに対する完全一致検索（高速・正確）
  2. ベクトル検索 — ChromaDBによるセマンティック検索（意味的類似度）

2段階アーキテクチャ:
  Stage 1: 軽量インデックス(_index.json) + ChromaDBで候補を特定
  Stage 2: マッチしたエントリのみソースJSONからフルコンテンツを取得

使い方:
    python3 scripts/search_persona.py "キーワード" [--top N] [--category CAT] [--mode MODE]

モード:
    hybrid  — キーワード + ベクトル検索を統合（デフォルト）
    keyword — キーワード検索のみ（ChromaDB不要）
    vector  — ベクトル検索のみ

例:
    python3 scripts/search_persona.py "転職 キャリア エンジニア"
    python3 scripts/search_persona.py "挑戦することの大切さ" --mode vector
    python3 scripts/search_persona.py "AI プログラミング" --top 5 --category ai_programming
"""

import json
import re
import sys
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# キーワード検索
# ---------------------------------------------------------------------------

def tokenize(text: str) -> set[str]:
    text = text.lower()
    tokens = set(re.split(r'[\s・/,、。]+', text))
    tokens.discard("")
    return tokens


def keyword_score(entry: dict, query_tokens: set[str],
                  category_filter: str | None) -> float:
    score = 0.0

    if category_filter:
        entry_cat = entry.get("category", "").lower()
        if category_filter.lower() not in entry_cat:
            return 0.0

    searchable_parts = []
    for field in ["title", "topic", "one_liner", "lesson", "summary",
                   "stance", "context", "counterpoint_summary"]:
        val = entry.get(field, "")
        if val:
            searchable_parts.append(val)

    tags = entry.get("tags", [])
    tag_text = " ".join(tags).lower()

    for field in ["values", "beliefs", "life_philosophy"]:
        vals = entry.get(field, [])
        if vals:
            searchable_parts.extend(vals)

    searchable_text = " ".join(searchable_parts).lower()

    for token in query_tokens:
        if token in tag_text:
            score += 3.0
        if token in searchable_text:
            score += 1.0

    type_bonus = {"episode": 1.5, "opinion": 1.3, "experience": 1.0,
                  "story": 1.2, "identity": 0.8}
    score *= type_bonus.get(entry.get("type", ""), 1.0)

    if entry.get("strength") == "strong":
        score *= 1.2

    return score


def keyword_search(index: dict, query: str, top_n: int,
                   category: str | None) -> list[tuple[float, dict]]:
    query_tokens = tokenize(query)
    scored = []
    for entry in index["entries"]:
        s = keyword_score(entry, query_tokens, category)
        if s > 0:
            scored.append((s, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# ベクトル検索 (ChromaDB)
# ---------------------------------------------------------------------------

def vector_search(query: str, db_dir: Path, top_n: int,
                  category: str | None) -> list[tuple[float, dict]]:
    try:
        import chromadb
    except ImportError:
        print("Warning: chromadb not installed, skipping vector search",
              file=sys.stderr)
        return []

    if not db_dir.exists():
        print(f"Warning: VectorDB not found at {db_dir}, skipping vector search",
              file=sys.stderr)
        return []

    client = chromadb.PersistentClient(
        path=str(db_dir),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection("persona_knowledge")
    except Exception:
        print("Warning: persona_knowledge collection not found", file=sys.stderr)
        return []

    where_filter = None
    if category:
        where_filter = {"category": {"$eq": category}}

    results = collection.query(
        query_texts=[query],
        n_results=min(top_n * 2, collection.count()),  # 多めに取得してマージ用に
        where=where_filter,
    )

    scored = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 1.0
            # cosine距離をスコアに変換 (0=完全一致 → score高い)
            similarity = max(0, 1.0 - distance)
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}

            # インデックスエントリを再構成
            entry = {
                "id": doc_id,
                "type": metadata.get("type", ""),
                "category": metadata.get("category", ""),
                "source": metadata.get("source", ""),
                "tags": json.loads(metadata.get("tags", "[]")),
            }

            # type_bonusを適用
            type_bonus = {"episode": 1.5, "opinion": 1.3, "experience": 1.0,
                          "story": 1.2, "identity": 0.8}
            score = similarity * 10.0 * type_bonus.get(entry["type"], 1.0)

            if score > 0.5:  # 閾値以下は除外
                scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# 結果マージ + フルコンテンツ取得
# ---------------------------------------------------------------------------

def merge_results(keyword_results: list[tuple[float, dict]],
                  vector_results: list[tuple[float, dict]],
                  top_n: int) -> list[tuple[float, dict]]:
    """キーワード検索とベクトル検索の結果をマージする。"""
    seen = {}

    # キーワード結果のスコアを正規化
    kw_max = max((s for s, _ in keyword_results), default=1.0)
    for score, entry in keyword_results:
        eid = entry["id"]
        normalized = (score / kw_max) * 10.0 if kw_max > 0 else 0
        seen[eid] = {"score": normalized, "entry": entry, "sources": ["keyword"]}

    # ベクトル結果をマージ
    for score, entry in vector_results:
        eid = entry["id"]
        if eid in seen:
            # 両方にマッチ → ボーナス付き合算
            seen[eid]["score"] += score * 0.7
            seen[eid]["sources"].append("vector")
        else:
            seen[eid] = {"score": score * 0.7, "entry": entry, "sources": ["vector"]}

    # 両方にマッチしたエントリにボーナス
    for eid, data in seen.items():
        if len(data["sources"]) > 1:
            data["score"] *= 1.3  # 双方マッチボーナス

    ranked = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
    return [(r["score"], r["entry"]) for r in ranked[:top_n]]


def resolve_source(source: str, persona_dir: Path) -> dict | None:
    parts = source.split("#", 1)
    if len(parts) != 2:
        return None

    file_name, json_path = parts
    file_path = persona_dir / file_name
    if not file_path.exists():
        return None

    data = json.loads(file_path.read_text())
    current = data
    for segment in re.split(r'\.', json_path):
        match = re.match(r'^(\w+)\[(\d+)\]$', segment)
        if match:
            key, idx = match.group(1), int(match.group(2))
            if isinstance(current, dict) and key in current:
                current = current[key]
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        else:
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            else:
                return None
    return current


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def search(query: str, persona_dir: Path, db_dir: Path, top_n: int = 5,
           category: str | None = None, mode: str = "hybrid") -> dict:
    index_path = persona_dir / "_index.json"
    if not index_path.exists():
        return {"error": f"Index not found at {index_path}. Run build_persona_index.py first."}

    index = json.loads(index_path.read_text())

    kw_results = []
    vec_results = []

    if mode in ("keyword", "hybrid"):
        kw_results = keyword_search(index, query, top_n * 2, category)

    if mode in ("vector", "hybrid"):
        vec_results = vector_search(query, db_dir, top_n * 2, category)

    if mode == "hybrid":
        final = merge_results(kw_results, vec_results, top_n)
    elif mode == "keyword":
        final = kw_results[:top_n]
    else:
        final = vec_results[:top_n]

    # フルコンテンツ取得
    results = []
    for score, entry in final:
        full_content = resolve_source(entry.get("source", ""), persona_dir)
        results.append({
            "id": entry.get("id", ""),
            "type": entry.get("type", ""),
            "category": entry.get("category", ""),
            "score": round(score, 2),
            "tags": entry.get("tags", []),
            "full_content": full_content,
        })

    return {
        "query": query,
        "mode": mode,
        "total_keyword_matches": len(kw_results),
        "total_vector_matches": len(vec_results),
        "returned": len(results),
        "voice_summary": index.get("voice_summary"),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="ペルソナナレッジ統合検索")
    parser.add_argument("query", help="検索キーワード（スペース区切り）")
    parser.add_argument("--top", type=int, default=5, help="返す件数（デフォルト: 5）")
    parser.add_argument("--category", help="カテゴリフィルタ")
    parser.add_argument("--mode", choices=["hybrid", "keyword", "vector"],
                        default="hybrid", help="検索モード（デフォルト: hybrid）")
    parser.add_argument("--persona-dir", help="ペルソナディレクトリのパス")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent.parent
    persona_dir = Path(args.persona_dir) if args.persona_dir else \
        base / "external" / "persona" / "knowledge" / "pao-pao-cho"
    db_dir = base / ".persona_vectordb"

    result = search(args.query, persona_dir, db_dir, args.top, args.category, args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
