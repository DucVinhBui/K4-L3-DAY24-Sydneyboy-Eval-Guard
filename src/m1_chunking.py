from __future__ import annotations

"""
Module 1: Advanced Chunking Strategies
=======================================
Implement semantic, hierarchical, và structure-aware chunking.
So sánh với basic chunking (baseline) để thấy improvement.

Test: pytest tests/test_m1.py
"""

import os, sys, glob, re
from dataclasses import dataclass, field

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (DATA_DIR, HIERARCHICAL_PARENT_SIZE, HIERARCHICAL_CHILD_SIZE,
                    SEMANTIC_THRESHOLD)


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    parent_id: str | None = None


def _extract_pdf_text(path: str) -> str:
    """Extract text layer từ PDF. Trả về "" nếu PDF là scan ảnh (không có text)."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def load_documents(data_dir: str = DATA_DIR) -> list[dict]:
    """Load tất cả markdown và PDF (có text layer) từ data/. (Đã implement sẵn)

    - .md: đọc trực tiếp.
    - .pdf: trích text layer bằng pypdf. PDF scan ảnh (không có text) bị bỏ qua
      kèm cảnh báo — RAG text-based không xử lý được scan nếu chưa OCR.
    """
    docs = []
    for fp in sorted(glob.glob(os.path.join(data_dir, "*.md"))):
        with open(fp, encoding="utf-8") as f:
            docs.append({"text": f.read(), "metadata": {"source": os.path.basename(fp)}})

    for fp in sorted(glob.glob(os.path.join(data_dir, "*.pdf"))):
        text = _extract_pdf_text(fp)
        if text:
            docs.append({"text": text, "metadata": {"source": os.path.basename(fp)}})
        else:
            print(f"  ⚠️  Bỏ qua {os.path.basename(fp)}: PDF scan ảnh, không có text layer (cần OCR).")

    return docs


# ─── Baseline: Basic Chunking (để so sánh) ──────────────


def chunk_basic(text: str, chunk_size: int = 500, metadata: dict | None = None) -> list[Chunk]:
    """
    Basic chunking: split theo paragraph (\\n\\n).
    Đây là baseline — KHÔNG phải mục tiêu của module này.
    (Đã implement sẵn)
    """
    metadata = metadata or {}
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for i, para in enumerate(paragraphs):
        if len(current) + len(para) > chunk_size and current:
            chunks.append(Chunk(text=current.strip(), metadata={**metadata, "chunk_index": len(chunks)}))
            current = ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(Chunk(text=current.strip(), metadata={**metadata, "chunk_index": len(chunks)}))
    return chunks


# ─── Strategy 1: Semantic Chunking ───────────────────────

_SENT_MODEL = None
_HEADER_RE = re.compile(r"^#{1,6}\s+")


def _get_sentence_model():
    """Cache model ở module-level để không load lại mỗi lần gọi."""
    global _SENT_MODEL
    if _SENT_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _SENT_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _SENT_MODEL


def chunk_semantic(text: str, threshold: float = SEMANTIC_THRESHOLD,
                   metadata: dict | None = None) -> list[Chunk]:
    """
    Split text by sentence similarity — nhóm câu cùng chủ đề.
    Tốt hơn basic vì không cắt giữa ý.
    """
    from numpy import dot
    from numpy.linalg import norm

    metadata = metadata or {}
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n\n", text) if s and s.strip()]
    if not sentences:
        return []

    embeddings = _get_sentence_model().encode(sentences)

    def cosine_sim(a, b):
        return float(dot(a, b) / (norm(a) * norm(b) + 1e-9))

    groups = [[sentences[0]]]
    for i in range(1, len(sentences)):
        sent = sentences[i]
        is_header = bool(_HEADER_RE.match(sent))
        prev_only_headers = all(_HEADER_RE.match(s) for s in groups[-1])
        if prev_only_headers and not is_header:
            # Header luôn đi cùng câu nội dung đầu tiên của nó
            groups[-1].append(sent)
        elif is_header and not prev_only_headers:
            # Header markdown = ranh giới chủ đề rõ ràng
            groups.append([sent])
        elif cosine_sim(embeddings[i - 1], embeddings[i]) < threshold:
            groups.append([sent])
        else:
            groups[-1].append(sent)

    return [
        Chunk(text="\n".join(g), metadata={**metadata, "chunk_index": i, "strategy": "semantic"})
        for i, g in enumerate(groups)
    ]


# ─── Strategy 2: Hierarchical Chunking ──────────────────


def _pack(units: list[str], max_size: int, sep: str) -> list[str]:
    """Gộp các đơn vị văn bản liên tiếp thành khối ≤ max_size ký tự."""
    blocks, current = [], ""
    for unit in units:
        if current and len(current) + len(sep) + len(unit) > max_size:
            blocks.append(current)
            current = unit
        else:
            current = f"{current}{sep}{unit}" if current else unit
    if current:
        blocks.append(current)
    return blocks


def _split_long(unit: str, max_size: int) -> list[str]:
    """Cắt 1 đơn vị quá dài theo từ để không vượt max_size."""
    if len(unit) <= max_size:
        return [unit]
    return _pack(unit.split(), max_size, " ")


def chunk_hierarchical(text: str, parent_size: int = HIERARCHICAL_PARENT_SIZE,
                       child_size: int = HIERARCHICAL_CHILD_SIZE,
                       metadata: dict | None = None) -> tuple[list[Chunk], list[Chunk]]:
    """
    Parent-child hierarchy: retrieve child (precision) → return parent (context).
    Đây là default recommendation cho production RAG.

    Returns:
        (parents, children) — mỗi child có parent_id link đến parent.
    """
    metadata = metadata or {}
    source = metadata.get("source", "")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    parent_units = []
    for para in paragraphs:
        if len(para) <= parent_size:
            parent_units.append(para)
        else:
            sents = [s for s in re.split(r"(?<=[.!?])\s+|\n", para) if s.strip()]
            parent_units.extend(_pack([u for s in sents for u in _split_long(s, parent_size)],
                                      parent_size, " "))

    parents, children = [], []
    for parent_text in _pack(parent_units, parent_size, "\n\n"):
        # Gắn source vào id để parent_id duy nhất trên toàn corpus
        pid = f"{source}::parent_{len(parents)}" if source else f"parent_{len(parents)}"
        parents.append(Chunk(text=parent_text,
                             metadata={**metadata, "chunk_type": "parent", "parent_id": pid}))

        child_units = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", parent_text) if s.strip()]
        child_units = [u for s in child_units for u in _split_long(s, child_size)]
        for j, child_text in enumerate(_pack(child_units, child_size, "\n")):
            children.append(Chunk(text=child_text,
                                  metadata={**metadata, "chunk_type": "child", "child_index": j},
                                  parent_id=pid))
    return parents, children


# ─── Strategy 3: Structure-Aware Chunking ────────────────


def chunk_structure_aware(text: str, metadata: dict | None = None) -> list[Chunk]:
    """
    Parse markdown headers → chunk theo logical structure.
    Giữ nguyên tables, code blocks, lists — không cắt giữa chừng.
    """
    metadata = metadata or {}
    parts = re.split(r"(^#{1,3}\s+.+$)", text, flags=re.MULTILINE)

    chunks: list[Chunk] = []
    header_stack: list[tuple[int, str]] = []  # (level, title)
    current_header = ""

    def _flush(content: str):
        content = content.strip()
        if not content:
            return
        section = header_stack[-1][1] if header_stack else ""
        body = f"{current_header}\n{content}" if current_header else content
        chunks.append(Chunk(text=body, metadata={
            **metadata,
            "section": section,
            "section_path": " > ".join(t for _, t in header_stack),
            "chunk_index": len(chunks),
            "strategy": "structure",
        }))

    for part in parts:
        m = re.match(r"^(#{1,3})\s+(.+)$", part.strip()) if part.strip() else None
        if m and "\n" not in part.strip():
            level, title = len(m.group(1)), m.group(2).strip()
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()
            header_stack.append((level, title))
            current_header = part.strip()
        else:
            _flush(part)
    return chunks


# ─── A/B Test: Compare All Strategies ────────────────────


def compare_strategies(documents: list[dict]) -> dict:
    """
    Run all strategies on documents and compare.
    (Đã implement sẵn — sẽ hoạt động khi bạn implement 3 strategies ở trên)
    """
    def _stats(chunk_list):
        lengths = [len(c.text) for c in chunk_list]
        if not lengths:
            return {"count": 0, "avg_len": 0, "min_len": 0, "max_len": 0}
        return {
            "count": len(lengths),
            "avg_len": round(sum(lengths) / len(lengths)),
            "min_len": min(lengths),
            "max_len": max(lengths),
        }

    all_text = "\n\n".join(d["text"] for d in documents)
    meta = {"source": "all"}

    basic = chunk_basic(all_text, metadata=meta)
    semantic = chunk_semantic(all_text, metadata=meta)
    parents, children = chunk_hierarchical(all_text, metadata=meta)
    structure = chunk_structure_aware(all_text, metadata=meta)

    results = {
        "basic": _stats(basic),
        "semantic": _stats(semantic),
        "hierarchical": {**_stats(children), "parents": len(parents)},
        "structure": _stats(structure),
    }

    print(f"{'Strategy':<15} {'Chunks':>7} {'Avg':>5} {'Min':>5} {'Max':>5}")
    for name, s in results.items():
        print(f"{name:<15} {s['count']:>7} {s['avg_len']:>5} {s['min_len']:>5} {s['max_len']:>5}")

    return results


if __name__ == "__main__":
    docs = load_documents()
    print(f"Loaded {len(docs)} documents")
    results = compare_strategies(docs)
    for name, stats in results.items():
        print(f"  {name}: {stats}")
