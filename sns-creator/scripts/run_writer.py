#!/usr/bin/env python3
"""
Writer Agent — ライターエージェント（最重要エージェント）

アイデア・分析結果・プロフィール情報を統合し、
投稿パターンに基づいてドラフトを生成する。

NOTE: 実際のテキスト生成・スコアリングはClaude Codeエージェントが
このフレームワークを使って実行する。このスクリプトはパターン選択、
ローテーション管理、品質チェック、NG語チェックの骨格を提供する。
"""

import argparse
import os
import sys
import re
from collections import Counter
from pathlib import Path

# スクリプトディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_json, save_json, setup_logging, timestamp_now, generate_id, PROJECT_ROOT

# ============================================================
# 15の投稿パターン定義
# ============================================================
POSTING_PATTERNS = [
    {
        "id": "hot_take",
        "name": "逆張り・ホットテイク",
        "type": "normal",
        "description": "常識の逆を突く主張で注目を集める",
        "template_prompt": (
            "以下のテーマについて、一般的な認識の逆を突く大胆な主張を含む投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、断言口調、1行目でインパクト"
        ),
    },
    {
        "id": "listicle",
        "name": "リスト型",
        "type": "normal",
        "description": "「○○する3つの方法」などリスト形式",
        "template_prompt": (
            "以下のテーマについて、3〜5個のポイントをリスト形式でまとめた投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、各ポイントは絵文字で始める、最後にまとめの一文"
        ),
    },
    {
        "id": "storytelling",
        "name": "ストーリーテリング",
        "type": "normal",
        "description": "個人体験や具体的なエピソードで語る",
        "template_prompt": (
            "以下のテーマについて、具体的なエピソードを交えたストーリー形式の投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、導入→展開→結論、感情に訴える"
        ),
    },
    {
        "id": "question_hook",
        "name": "問いかけ型",
        "type": "comment_hook",
        "description": "質問で始めてコメントを促す。自分コメントでフック",
        "template_prompt": (
            "以下のテーマについて、読者への問いかけで始まる投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 本文は質問+背景説明（300文字以内）\n"
            "追加: 自分で最初のコメントとして回答例を付ける（200文字以内）"
        ),
        "comment_template": "自分の回答として: {self_answer}",
    },
    {
        "id": "data_driven",
        "name": "データ・数字型",
        "type": "normal",
        "description": "具体的な数字やデータを提示して説得力を出す",
        "template_prompt": (
            "以下のテーマについて、具体的な数字やデータを含む投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、最低2つの具体的数字を含む、出典は省略可"
        ),
    },
    {
        "id": "comparison",
        "name": "比較型",
        "type": "normal",
        "description": "AとBを比較して気づきを提供",
        "template_prompt": (
            "以下のテーマについて、2つの概念を比較する投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、A vs B形式、最後に自分の見解"
        ),
    },
    {
        "id": "thread_deep_dive",
        "name": "スレッド深掘り",
        "type": "thread",
        "description": "3〜5投稿のスレッドで深く解説",
        "template_prompt": (
            "以下のテーマについて、3〜5つの連続投稿（スレッド）を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 1投稿あたり300文字以内、各投稿が独立して読めること\n"
            "構成: 1.導入+問題提起 → 2.本論 → 3.具体例 → 4.結論+アクション"
        ),
    },
    {
        "id": "behind_the_scenes",
        "name": "裏側・舞台裏",
        "type": "normal",
        "description": "普段見せない裏側やプロセスを公開",
        "template_prompt": (
            "以下のテーマについて、裏側やプロセスを公開する投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、「実は…」で始める、具体的な手順や失敗談を含む"
        ),
    },
    {
        "id": "myth_busting",
        "name": "誤解を解く",
        "type": "normal",
        "description": "よくある誤解を指摘して正しい情報を提供",
        "template_prompt": (
            "以下のテーマについて、よくある誤解を指摘する投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、「多くの人が誤解しているが…」形式、エビデンス付き"
        ),
    },
    {
        "id": "quick_tip",
        "name": "即効Tips",
        "type": "normal",
        "description": "今すぐ使える具体的なテクニック",
        "template_prompt": (
            "以下のテーマについて、すぐに実践できるTipsを1つ紹介する投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 300文字以内、具体的な手順、「今日からできる」感"
        ),
    },
    {
        "id": "prediction",
        "name": "予測・未来予想",
        "type": "normal",
        "description": "トレンド予測や未来の展望を語る",
        "template_prompt": (
            "以下のテーマについて、今後の予測や展望を語る投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、根拠を示す、「3年後には…」など具体的時期"
        ),
    },
    {
        "id": "before_after",
        "name": "ビフォーアフター",
        "type": "normal",
        "description": "変化の前後を対比して見せる",
        "template_prompt": (
            "以下のテーマについて、ビフォーアフター形式の投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 500文字以内、Before/After明確、変化のきっかけを含む"
        ),
    },
    {
        "id": "curated_picks",
        "name": "おすすめ紹介",
        "type": "affiliate",
        "description": "ツール・本・サービスのおすすめ（アフィリエイト可）",
        "template_prompt": (
            "以下のテーマに関連するおすすめツール/本/サービスを紹介する投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 本文300文字以内、自然な紹介\n"
            "追加: コメントにアフィリエイトリンクを含む補足情報（200文字以内）"
        ),
        "affiliate_comment_template": "詳細はこちら: {link}\n{supplementary_info}",
    },
    {
        "id": "poll_style",
        "name": "投票・アンケート型",
        "type": "comment_hook",
        "description": "二択や多択の投票でエンゲージメント獲得",
        "template_prompt": (
            "以下のテーマについて、読者に選択肢を提示する投票形式の投稿を作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 本文200文字以内、A/B二択、コメントで投票を促す\n"
            "追加: 自分コメントで「自分はA派。理由は…」と書く（150文字以内）"
        ),
        "comment_template": "自分は{choice}派。理由は{reason}",
    },
    {
        "id": "framework",
        "name": "フレームワーク提示",
        "type": "thread",
        "description": "思考フレームワークやテンプレートを共有",
        "template_prompt": (
            "以下のテーマについて、実用的なフレームワークを紹介するスレッドを作成してください。\n"
            "テーマ: {theme}\nアイデア: {idea}\n"
            "要件: 2〜4投稿のスレッド\n"
            "構成: 1.フレームワーク名と概要 → 2.各ステップ説明 → 3.使用例"
        ),
    },
]

# スコアリング基準（10項目）
SCORING_CRITERIA = [
    {"id": "hook", "name": "フック力", "description": "最初の1行で止まるか", "weight": 1.5},
    {"id": "value", "name": "価値提供", "description": "読者にとっての具体的価値", "weight": 1.5},
    {"id": "clarity", "name": "明瞭さ", "description": "メッセージが明確か", "weight": 1.0},
    {"id": "emotion", "name": "感情喚起", "description": "感情を動かすか", "weight": 1.0},
    {"id": "actionable", "name": "実用性", "description": "すぐ使える情報か", "weight": 1.0},
    {"id": "uniqueness", "name": "独自性", "description": "他と差別化されているか", "weight": 1.2},
    {"id": "shareability", "name": "共有性", "description": "シェアしたくなるか", "weight": 1.0},
    {"id": "brand_fit", "name": "ブランド適合", "description": "プロフィールと一致するか", "weight": 0.8},
    {"id": "length", "name": "長さ適正", "description": "パターンに適した長さか", "weight": 0.5},
    {"id": "cta", "name": "CTA", "description": "次のアクションを促すか", "weight": 0.5},
]

# 類似度チェックの閾値
SIMILARITY_THRESHOLD = 0.85

# NG語チェック
MAX_REWRITES = 2

# スコア閾値
MIN_SCORE = 7.0


def parse_args():
    parser = argparse.ArgumentParser(description="Writer Agent: ドラフト生成")
    parser.add_argument("--account", "-a", default=os.environ.get("ACTIVE_ACCOUNT", "default"), help="アカウントID")
    parser.add_argument("--batch-size", type=int, default=5, help="一度に生成するドラフト数（5-10）")
    parser.add_argument("--dry-run", action="store_true", help="ファイルに保存しない")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")
    return parser.parse_args()


def get_recent_patterns(posts: list, n: int = 3) -> list[str]:
    """直近N件の投稿パターンを取得"""
    recent = sorted(
        [p for p in posts if p.get("posted_at")],
        key=lambda x: x.get("posted_at", ""),
        reverse=True,
    )[:n]
    return [p.get("pattern", "") for p in recent]


def get_recent_themes(posts: list, n: int = 3) -> list[str]:
    """直近N件の投稿テーマを取得"""
    recent = sorted(
        [p for p in posts if p.get("posted_at")],
        key=lambda x: x.get("posted_at", ""),
        reverse=True,
    )[:n]
    return [p.get("theme", "") for p in recent]


def select_pattern(recent_patterns: list, preferred: list, avoid: list) -> dict | None:
    """パターンローテーションに基づいてパターンを選択する"""
    # 使用可能なパターンをフィルタリング
    candidates = []
    for pattern in POSTING_PATTERNS:
        pid = pattern["id"]

        # 直近で使用されたパターンは除外
        if pid in recent_patterns:
            continue

        # 回避パターンは除外（ただし候補が少なすぎる場合は含める）
        if pid in avoid:
            continue

        candidates.append(pattern)

    if not candidates:
        # 回避パターンも含めて再試行
        candidates = [p for p in POSTING_PATTERNS if p["id"] not in recent_patterns]

    if not candidates:
        # それでもなければ全パターンから
        candidates = list(POSTING_PATTERNS)

    # 優先パターンを先頭に
    preferred_candidates = [c for c in candidates if c["id"] in preferred]
    other_candidates = [c for c in candidates if c["id"] not in preferred]

    ordered = preferred_candidates + other_candidates

    return ordered[0] if ordered else None


def select_idea(ideas: list, target_theme: str | None = None) -> dict | None:
    """未使用のアイデアを選択する"""
    unused = [i for i in ideas if not i.get("used", False)]

    if target_theme:
        themed = [i for i in unused if i.get("theme") == target_theme]
        if themed:
            return themed[0]

    return unused[0] if unused else None


def check_theme_rotation(recent_themes: list, candidate_theme: str) -> bool:
    """テーマが3回連続していないかチェック（True=OK, False=要切替）"""
    if len(recent_themes) < 3:
        return True
    return not all(t == candidate_theme for t in recent_themes[:3])


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    2つのテキスト間の類似度を計算する（簡易版: 単語ベース）

    NOTE: 本番ではより高度な類似度計算を使用すべき
    （例: TF-IDF, コサイン類似度, sentence-transformers等）
    """
    if not text1 or not text2:
        return 0.0

    # 単語分割（日本語は文字単位で分割）
    def tokenize(text: str) -> set:
        # 英数字の単語
        words = set(re.findall(r'[a-zA-Z0-9]+', text.lower()))
        # 日本語はbi-gram
        chars = re.sub(r'[a-zA-Z0-9\s\W]+', '', text)
        bigrams = {chars[i:i+2] for i in range(len(chars) - 1)}
        return words | bigrams

    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union) if union else 0.0


def check_similarity_against_history(text: str, past_posts: list, threshold: float = SIMILARITY_THRESHOLD) -> tuple[bool, float]:
    """
    過去の投稿との類似度をチェック
    Returns: (is_similar, max_similarity)
    """
    max_sim = 0.0

    # 直近100件をチェック
    recent_posts = past_posts[-100:]

    for post in recent_posts:
        post_text = post.get("text", "")
        if not post_text:
            continue
        sim = calculate_text_similarity(text, post_text)
        max_sim = max(max_sim, sim)
        if sim >= threshold:
            return True, sim

    return False, max_sim


def check_ng_words(text: str, ng_words: list[str]) -> list[str]:
    """NGワードチェック。見つかったNGワードのリストを返す"""
    found = []
    text_lower = text.lower()
    for word in ng_words:
        if word.lower() in text_lower:
            found.append(word)
    return found


def generate_post_content(pattern: dict, idea: dict, profile: dict, instructions: dict) -> dict:
    """
    投稿コンテンツを生成する（プレースホルダー）

    NOTE: 実際の生成はClaude Codeエージェントがこの関数の代わりに
    LLMを使って行う。このプレースホルダーはフレームワークの動作確認用。

    Returns:
        dict: {
            "text": str,              # メイン投稿テキスト
            "comment_text": str|None,  # コメントフック用テキスト
            "thread_texts": list|None, # スレッド用テキストリスト
            "affiliate_comment": str|None,  # アフィリエイトコメント
        }
    """
    theme = idea.get("theme", "テーマなし")
    idea_text = idea.get("text", idea.get("title", "アイデアなし"))

    # プレースホルダーテキスト
    # 実際にはClaude CodeがLLMで生成する
    placeholder_text = (
        f"[PLACEHOLDER - Claude Codeが生成]\n"
        f"パターン: {pattern['name']}\n"
        f"テーマ: {theme}\n"
        f"アイデア: {idea_text}\n"
        f"プロンプト: {pattern['template_prompt'].format(theme=theme, idea=idea_text)}"
    )

    result = {
        "text": placeholder_text,
        "comment_text": None,
        "thread_texts": None,
        "affiliate_comment": None,
    }

    if pattern["type"] == "comment_hook":
        result["comment_text"] = f"[PLACEHOLDER - コメント] {pattern.get('comment_template', '')}"
    elif pattern["type"] == "thread":
        result["thread_texts"] = [
            f"[PLACEHOLDER - スレッド {i+1}]" for i in range(3)
        ]
    elif pattern["type"] == "affiliate":
        result["affiliate_comment"] = (
            f"[PLACEHOLDER - アフィリエイトコメント] "
            f"{pattern.get('affiliate_comment_template', '')}"
        )

    return result


def score_post(text: str, pattern: dict, profile: dict) -> dict:
    """
    投稿をスコアリングする（プレースホルダー）

    NOTE: 実際のスコアリングはClaude Codeエージェントが
    LLMを使って各基準を評価する。

    Returns:
        dict: {"total": float, "criteria": {criterion_id: score, ...}}
    """
    # プレースホルダー: 全基準に仮スコアを付与
    # 実際にはClaude Codeが各基準を1-10で評価する
    criteria_scores = {}
    total_weighted = 0.0
    total_weight = 0.0

    for criterion in SCORING_CRITERIA:
        # プレースホルダースコア（実際にはLLMが評価）
        score = 7.5  # デフォルト仮スコア
        criteria_scores[criterion["id"]] = {
            "score": score,
            "weight": criterion["weight"],
            "weighted": score * criterion["weight"],
        }
        total_weighted += score * criterion["weight"]
        total_weight += criterion["weight"]

    total_score = total_weighted / total_weight if total_weight > 0 else 0

    return {
        "total": round(total_score, 2),
        "criteria": criteria_scores,
        "scoring_method": "placeholder",  # "llm" に変更（Claude Code実行時）
    }


def main():
    args = parse_args()
    logger = setup_logging("writer", verbose=args.verbose)

    logger.info("=== Writer Agent 開始 ===")
    if args.dry_run:
        logger.info("[DRY-RUN モード]")

    batch_size = max(1, min(10, args.batch_size))
    logger.info(f"バッチサイズ: {batch_size}")

    # パス設定
    account_path = PROJECT_ROOT / "data" / args.account
    account_path.mkdir(parents=True, exist_ok=True)
    ideas_path = account_path / "research" / "ideas.json"
    analysis_path = account_path / "analysis" / "latest.json"
    profile_path = account_path / "knowledge" / "profile.json"
    ng_words_path = account_path / "knowledge" / "ng_words.json"
    posts_path = account_path / "history" / "posts.json"
    drafts_path = account_path / "drafts" / "pool.json"

    # データ読み込み
    ideas_data = load_json(ideas_path, default={"ideas": []})
    ideas = ideas_data.get("ideas", [])

    analysis = load_json(analysis_path, default={})
    writer_instructions = analysis.get("writer_instructions", {})

    profile = load_json(profile_path, default={})
    ng_words_data = load_json(ng_words_path, default={"words": []})
    ng_words = ng_words_data.get("words", [])

    posts_data = load_json(posts_path, default={"posts": []})
    posts = posts_data.get("posts", [])

    drafts_data = load_json(drafts_path, default={"drafts": []})
    drafts = drafts_data.get("drafts", [])

    # 分析結果から優先/回避パターンを取得
    preferred_patterns = writer_instructions.get("preferred_patterns", [])
    avoid_patterns = writer_instructions.get("avoid_patterns", [])

    # 直近の投稿パターンとテーマ
    recent_patterns = get_recent_patterns(posts, n=3)
    recent_themes = get_recent_themes(posts, n=3)

    logger.info(f"直近パターン: {recent_patterns}")
    logger.info(f"直近テーマ: {recent_themes}")
    logger.info(f"優先パターン: {preferred_patterns}")
    logger.info(f"回避パターン: {avoid_patterns}")

    # ドラフト生成
    generated_count = 0
    rejected_count = 0
    new_drafts = []

    for i in range(batch_size):
        logger.info(f"--- ドラフト生成 {i+1}/{batch_size} ---")

        # 1. アイデア選択
        idea = select_idea(ideas)
        if idea is None:
            logger.warning("未使用アイデアが枯渇しました。リサーチが必要です。")
            break

        idea_theme = idea.get("theme", "general")

        # 2. テーマローテーションチェック
        if not check_theme_rotation(recent_themes, idea_theme):
            logger.info(f"テーマ「{idea_theme}」が3回連続のため、別テーマを試行")
            # 別テーマのアイデアを探す
            alt_idea = None
            for candidate in ideas:
                if not candidate.get("used", False) and candidate.get("theme") != idea_theme:
                    alt_idea = candidate
                    break
            if alt_idea:
                idea = alt_idea
                idea_theme = idea.get("theme", "general")
            else:
                logger.warning("別テーマのアイデアがありません。同テーマで続行。")

        # 3. パターン選択（ローテーション考慮）
        # 前の生成で使ったパターンも含めて除外
        used_in_batch = [d.get("pattern") for d in new_drafts]
        exclude_patterns = list(set(recent_patterns + used_in_batch))

        pattern = select_pattern(exclude_patterns, preferred_patterns, avoid_patterns)
        if pattern is None:
            logger.error("有効なパターンが見つかりません。")
            break

        logger.info(f"選択: テーマ={idea_theme}, パターン={pattern['name']}, タイプ={pattern['type']}")

        # 4. コンテンツ生成（プレースホルダー）
        content = generate_post_content(pattern, idea, profile, writer_instructions)
        text = content["text"]

        # 5. スコアリング（プレースホルダー）
        rewrite_count = 0
        score_result = score_post(text, pattern, profile)

        while score_result["total"] < MIN_SCORE and rewrite_count < MAX_REWRITES:
            rewrite_count += 1
            logger.info(
                f"スコア不足 ({score_result['total']:.1f} < {MIN_SCORE})。"
                f"リライト {rewrite_count}/{MAX_REWRITES}"
            )
            # NOTE: 実際のリライトはClaude Codeが行う
            content = generate_post_content(pattern, idea, profile, writer_instructions)
            text = content["text"]
            score_result = score_post(text, pattern, profile)

        if score_result["total"] < MIN_SCORE:
            logger.warning(
                f"スコア不足で却下: {score_result['total']:.1f} < {MIN_SCORE} "
                f"(リライト{MAX_REWRITES}回実施済み)"
            )
            rejected_count += 1
            continue

        # 6. 類似度チェック
        is_similar, max_sim = check_similarity_against_history(text, posts)
        if is_similar:
            logger.warning(f"類似度が高すぎます: {max_sim:.2f} >= {SIMILARITY_THRESHOLD}")
            rejected_count += 1
            continue

        # 7. NGワードチェック
        found_ng = check_ng_words(text, ng_words)
        if found_ng:
            logger.warning(f"NGワード検出: {found_ng}")
            rejected_count += 1
            continue

        # コメントテキストもNGチェック
        for extra_text in [content.get("comment_text"), content.get("affiliate_comment")]:
            if extra_text:
                found_ng = check_ng_words(extra_text, ng_words)
                if found_ng:
                    logger.warning(f"コメントにNGワード検出: {found_ng}")
                    rejected_count += 1
                    continue

        if content.get("thread_texts"):
            for thread_text in content["thread_texts"]:
                found_ng = check_ng_words(thread_text, ng_words)
                if found_ng:
                    logger.warning(f"スレッドテキストにNGワード検出: {found_ng}")
                    rejected_count += 1
                    continue

        # 8. ドラフトとして保存
        draft = {
            "id": generate_id("draft"),
            "status": "draft",
            "pattern": pattern["id"],
            "pattern_name": pattern["name"],
            "type": pattern["type"],
            "theme": idea_theme,
            "idea_id": idea.get("id"),
            "text": text,
            "comment_text": content.get("comment_text"),
            "thread_texts": content.get("thread_texts"),
            "affiliate_comment": content.get("affiliate_comment"),
            "score": score_result,
            "similarity_max": round(max_sim, 3),
            "rewrite_count": rewrite_count,
            "created_at": timestamp_now(),
            "generated_by": "writer_agent",
        }

        new_drafts.append(draft)
        generated_count += 1

        # 9. アイデアを使用済みに
        idea["used"] = True
        idea["used_at"] = timestamp_now()
        idea["used_in_draft"] = draft["id"]

        logger.info(
            f"ドラフト生成成功: id={draft['id']}, "
            f"score={score_result['total']:.1f}, "
            f"similarity={max_sim:.3f}"
        )

    # 結果を保存
    if not args.dry_run and new_drafts:
        # ドラフトプールに追加
        drafts.extend(new_drafts)
        drafts_data["drafts"] = drafts
        drafts_data["last_generation"] = timestamp_now()
        save_json(drafts_path, drafts_data)
        logger.info(f"ドラフトを保存しました: {len(new_drafts)}件 → {drafts_path}")

        # アイデアの使用状態を保存
        ideas_data["ideas"] = ideas
        save_json(ideas_path, ideas_data)
        logger.info(f"アイデアの使用状態を更新しました: {ideas_path}")
    elif args.dry_run:
        logger.info("[DRY-RUN] 保存をスキップしました")

    # サマリー
    logger.info("=== Writer Agent 完了 ===")
    logger.info(f"生成: {generated_count}件, 却下: {rejected_count}件")
    logger.info(f"ドラフトプール合計: {len(drafts) + len(new_drafts)}件")

    return 0 if generated_count > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
