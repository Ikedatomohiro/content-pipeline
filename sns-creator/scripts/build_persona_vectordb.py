#!/usr/bin/env python3
"""
ペルソナナレッジをChromaDBにベクトルインデックスとして格納する。

各エントリのテキストをembeddingに変換し、永続化されたChromaDBに保存する。
これにより、キーワード完全一致に頼らないセマンティック検索が可能になる。

使い方:
    python3 scripts/build_persona_vectordb.py [persona_dir]
    デフォルト: external/persona/knowledge/pao-pao-cho

永続化先: .persona_vectordb/ (プロジェクトルート)
"""

import json
import sys
from pathlib import Path

import chromadb


def entry_to_document(entry: dict) -> str:
    """インデックスエントリを検索用テキストに変換する。"""
    parts = []

    # タイプ別に最適なテキストを構成
    entry_type = entry.get("type", "")

    if entry_type == "episode":
        parts.append(f"エピソード: {entry.get('title', '')}")
        parts.append(entry.get("one_liner", ""))
        parts.append(f"教訓: {entry.get('lesson', '')}")

    elif entry_type == "opinion":
        parts.append(f"意見: {entry.get('topic', '')}")
        parts.append(f"スタンス: {entry.get('stance', '')}")
        if entry.get("counterpoint_summary"):
            parts.append(f"反論: {entry['counterpoint_summary']}")

    elif entry_type == "experience":
        parts.append(f"経験: {entry.get('summary', '')}")
        parts.append(f"教訓: {entry.get('lesson', '')}")

    elif entry_type == "story":
        parts.append(f"ストーリー: {entry.get('summary', '')}")
        parts.append(f"文脈: {entry.get('context', '')}")

    elif entry_type == "identity":
        for v in entry.get("values", []):
            parts.append(f"価値観: {v}")
        for b in entry.get("beliefs", []):
            parts.append(f"信念: {b}")
        for p in entry.get("life_philosophy", []):
            parts.append(f"人生哲学: {p}")

    # タグも含める
    tags = entry.get("tags", [])
    if tags:
        parts.append(f"タグ: {', '.join(tags)}")

    return "\n".join(p for p in parts if p)


def build_vectordb(persona_dir: Path, db_dir: Path):
    """インデックスからChromaDBを構築する。"""
    index_path = persona_dir / "_index.json"
    if not index_path.exists():
        print("Error: _index.json not found. Run 'python3 scripts/build_index.py' in the persona repo first.",
              file=sys.stderr)
        sys.exit(1)

    index = json.loads(index_path.read_text())
    entries = index["entries"]

    # ChromaDB初期化（永続化）
    client = chromadb.PersistentClient(
        path=str(db_dir),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )

    # コレクションを再作成（既存があれば削除して最新に）
    collection_name = "persona_knowledge"
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    # ChromaDBのデフォルトembedding（all-MiniLM-L6-v2）を使用
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    documents = []
    metadatas = []
    ids = []

    for entry in entries:
        doc = entry_to_document(entry)
        if not doc.strip():
            continue

        documents.append(doc)
        metadatas.append({
            "id": entry["id"],
            "type": entry["type"],
            "category": entry.get("category", ""),
            "source": entry.get("source", ""),
            "tags": json.dumps(entry.get("tags", []), ensure_ascii=False),
        })
        ids.append(entry["id"])

    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)

    print(f"VectorDB built: {len(documents)} entries → {db_dir}")
    print(f"Collection: {collection_name}")


def main():
    # sns-creator/scripts/ → sns-creator/ → repo root
    repo_root = Path(__file__).resolve().parent.parent.parent
    if len(sys.argv) > 1:
        persona_dir = Path(sys.argv[1])
    else:
        persona_dir = repo_root / "external" / "persona" / "knowledge" / "pao-pao-cho"

    db_dir = repo_root / ".persona_vectordb"
    build_vectordb(persona_dir, db_dir)


if __name__ == "__main__":
    main()
