from __future__ import annotations

"""
Module 5: Enrichment Pipeline
==============================
Làm giàu chunks TRƯỚC khi embed: Summarize, HyQA, Contextual Prepend, Auto Metadata.

Test: pytest tests/test_m5.py
"""

import os, sys, re, json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY


@dataclass
class EnrichedChunk:
    """Chunk đã được làm giàu."""
    original_text: str
    enriched_text: str
    summary: str
    hypothesis_questions: list[str]
    auto_metadata: dict
    method: str  # "contextual", "summary", "hyqa", "full"


ENRICH_MODEL = "gpt-4o-mini"
_CLIENT = None


def _chat(system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
    """Gọi OpenAI chat completion (client dùng chung). Raise nếu lỗi."""
    global _CLIENT
    if _CLIENT is None:
        from openai import OpenAI
        _CLIENT = OpenAI(max_retries=5)
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = _CLIENT.chat.completions.create(
        model=ENRICH_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0,
        **kwargs,
    )
    return resp.choices[0].message.content.strip()


# ─── Technique 1: Chunk Summarization ────────────────────


def _extractive_summary(text: str) -> str:
    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    return ". ".join(sentences[:2]).rstrip(".") + "." if sentences else text


def summarize_chunk(text: str) -> str:
    """
    Tạo summary ngắn cho chunk.
    Embed summary thay vì (hoặc cùng với) raw chunk → giảm noise.
    """
    if OPENAI_API_KEY:
        try:
            return _chat("Tóm tắt đoạn văn sau trong 2-3 câu ngắn gọn bằng tiếng Việt.", text, 150)
        except Exception as e:
            print(f"  ⚠️  OpenAI summarize failed: {e}")
    # Extractive fallback (không cần API)
    return _extractive_summary(text)


# ─── Technique 2: Hypothesis Question-Answer (HyQA) ─────


def _extractive_questions(text: str, n_questions: int) -> list[str]:
    sentences = [s.strip() for s in re.split(r"[.!?\n]", text) if len(s.strip()) > 10]
    return [f"{s.lstrip('#> ').rstrip('.')}?" for s in sentences[:n_questions]]


def generate_hypothesis_questions(text: str, n_questions: int = 3) -> list[str]:
    """
    Generate câu hỏi mà chunk có thể trả lời.
    Index cả questions lẫn chunk → query match tốt hơn (bridge vocabulary gap).
    """
    if OPENAI_API_KEY:
        try:
            content = _chat(
                f"Dựa trên đoạn văn, tạo {n_questions} câu hỏi bằng tiếng Việt mà đoạn văn có thể trả lời. "
                "Trả về mỗi câu hỏi trên 1 dòng, không đánh số.",
                text, 200)
            questions = [q.strip().lstrip("0123456789.-) ") for q in content.split("\n") if q.strip()]
            return questions[:n_questions]
        except Exception as e:
            print(f"  ⚠️  OpenAI HyQA failed: {e}")
    # Extractive fallback
    return _extractive_questions(text, n_questions)


# ─── Technique 3: Contextual Prepend (Anthropic style) ──


def contextual_prepend(text: str, document_title: str = "") -> str:
    """
    Prepend context giải thích chunk nằm ở đâu trong document.
    Anthropic benchmark: giảm 49% retrieval failure (alone).
    """
    if OPENAI_API_KEY:
        try:
            context = _chat(
                "Viết 1 câu ngắn mô tả đoạn văn này nằm ở đâu trong tài liệu và nói về chủ đề gì. Chỉ trả về 1 câu.",
                f"Tài liệu: {document_title}\n\nĐoạn văn:\n{text}", 80)
            return f"{context}\n\n{text}"
        except Exception as e:
            print(f"  ⚠️  OpenAI contextual failed: {e}")
    # Simple fallback
    prefix = f"Trích từ {document_title}. " if document_title else ""
    return f"{prefix}{text}"


# ─── Technique 4: Auto Metadata Extraction ──────────────

_DEFAULT_METADATA = {"topic": "general", "entities": [], "category": "policy", "language": "vi"}


def extract_metadata(text: str) -> dict:
    """
    LLM extract metadata tự động: topic, entities, date_range, category.
    """
    if OPENAI_API_KEY:
        try:
            content = _chat(
                'Trích xuất metadata từ đoạn văn. Trả về JSON: {"topic": "...", "entities": ["..."], '
                '"category": "policy|hr|it|finance", "language": "vi|en"}',
                text, 150, json_mode=True)
            return json.loads(content)
        except Exception as e:
            print(f"  ⚠️  OpenAI metadata failed: {e}")
    return dict(_DEFAULT_METADATA)


# ─── Combined Single-Call Mode ───────────────────────────

_COMBINED_PROMPT = """Bạn làm giàu (enrich) một đoạn văn trích từ tài liệu nội bộ công ty để phục vụ tìm kiếm.
Trả về JSON đúng schema:
{
  "summary": "tóm tắt 2-3 câu",
  "questions": ["câu hỏi 1", "câu hỏi 2", "câu hỏi 3"],
  "context": "1-2 câu mô tả đoạn văn nằm ở đâu trong tài liệu: tên chính sách, phiên bản/ngày hiệu lực (nếu có), chủ đề của đoạn",
  "metadata": {"topic": "...", "entities": ["..."], "category": "policy|hr|it|finance", "language": "vi|en"}
}
- "questions": câu hỏi tự nhiên mà nhân viên có thể hỏi và đoạn văn trả lời được.
- Nếu tài liệu là phiên bản cũ đã bị thay thế, ghi rõ điều đó trong "context".
- Viết bằng tiếng Việt, không bịa thông tin ngoài tài liệu."""


def _enrich_single_call(text: str, source: str, document: str = "") -> dict:
    """Single LLM call to get summary + questions + context + metadata.

    ⚠️ Cost optimization: 1 API call thay vì 4 calls riêng lẻ.
    `document`: toàn văn tài liệu gốc (Anthropic contextual retrieval) — giúp
    LLM biết chunk thuộc phiên bản/phần nào của tài liệu.
    """
    if OPENAI_API_KEY:
        try:
            doc_block = f"<document>\n{document[:6000]}\n</document>\n\n" if document else ""
            content = _chat(_COMBINED_PROMPT,
                            f"Tài liệu: {source}\n\n{doc_block}Đoạn văn cần enrich:\n{text}",
                            500, json_mode=True)
            result = json.loads(content)
            if isinstance(result.get("questions"), list) and isinstance(result.get("metadata", {}), dict):
                return result
        except Exception as e:
            print(f"  ⚠️  Enrichment API failed: {e}")
    # Offline fallback (không cần API): vẫn có context + summary + questions
    return {
        "summary": _extractive_summary(text),
        "questions": _extractive_questions(text, 3),
        "context": f"Trích từ tài liệu {source}." if source else "",
        "metadata": dict(_DEFAULT_METADATA),
    }


# ─── Full Enrichment Pipeline ────────────────────────────


def enrich_chunks(
    chunks: list[dict],
    methods: list[str] | None = None,
    documents: dict[str, str] | None = None,
    max_workers: int = 8,
) -> list[EnrichedChunk]:
    """
    Chạy enrichment pipeline trên danh sách chunks.

    Có 2 chế độ:
    - methods cụ thể (["summary"], ["contextual"]...): gọi từng function riêng (tốt cho học/debug)
    - methods=["combined"] hoặc None: 1 API call duy nhất cho tất cả (tốt cho production)

    Args:
        chunks: List of {"text": str, "metadata": dict}
        methods: Default None → combined mode (1 call/chunk).
                 Options: "summary", "hyqa", "contextual", "metadata", "combined"
        documents: Optional {source: full_text} — toàn văn tài liệu cho contextual enrichment.
        max_workers: Số luồng gọi API song song (I/O-bound).
    """
    from concurrent.futures import ThreadPoolExecutor

    if methods is None:
        methods = ["combined"]
    use_combined = "combined" in methods
    documents = documents or {}

    def _enrich_one(chunk: dict) -> EnrichedChunk:
        text = chunk["text"]
        source = chunk.get("metadata", {}).get("source", "")

        if use_combined:
            result = _enrich_single_call(text, source, documents.get(source, ""))
            summary = result.get("summary", "")
            questions = [q for q in result.get("questions", []) if isinstance(q, str)]
            context_line = result.get("context", "")
            enriched_text = f"{context_line}\n\n{text}" if context_line else text
            auto_meta = result.get("metadata", {}) or {}
        else:
            summary = summarize_chunk(text) if "summary" in methods else ""
            questions = generate_hypothesis_questions(text) if "hyqa" in methods else []
            enriched_text = contextual_prepend(text, source) if "contextual" in methods else text
            auto_meta = extract_metadata(text) if "metadata" in methods else {}

        return EnrichedChunk(
            original_text=text,
            enriched_text=enriched_text,
            summary=summary,
            hypothesis_questions=questions,
            auto_metadata={**chunk.get("metadata", {}), **auto_meta},
            method="+".join(methods),
        )

    enriched: list[EnrichedChunk] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for i, item in enumerate(pool.map(_enrich_one, chunks)):  # map giữ nguyên thứ tự
            enriched.append(item)
            if (i + 1) % 10 == 0 or (i + 1) == len(chunks):
                print(f"  Enriched {i + 1}/{len(chunks)} chunks...", flush=True)

    return enriched


# ─── Main ────────────────────────────────────────────────

if __name__ == "__main__":
    sample = "Nhân viên chính thức được nghỉ phép năm 12 ngày làm việc mỗi năm. Số ngày nghỉ phép tăng thêm 1 ngày cho mỗi 5 năm thâm niên công tác."

    print("=== Enrichment Pipeline Demo ===\n")
    print(f"Original: {sample}\n")

    s = summarize_chunk(sample)
    print(f"Summary: {s}\n")

    qs = generate_hypothesis_questions(sample)
    print(f"HyQA questions: {qs}\n")

    ctx = contextual_prepend(sample, "Sổ tay nhân viên VinUni 2024")
    print(f"Contextual: {ctx}\n")

    meta = extract_metadata(sample)
    print(f"Auto metadata: {meta}")
