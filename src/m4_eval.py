from __future__ import annotations

"""Module 4: RAGAS Evaluation — 4 metrics + failure analysis."""

import os, sys, json, math
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_SET_PATH, OPENAI_API_KEY


@dataclass
class EvalResult:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def load_test_set(path: str = TEST_SET_PATH) -> list[dict]:
    """Load test set from JSON. (Đã implement sẵn)"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
RAGAS_LLM_MODEL = "gpt-4o-mini"
RAGAS_EMBEDDING_MODEL = "text-embedding-3-small"


RAGAS_MAX_ATTEMPTS = 3


def _is_finite(value) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def _run_ragas(questions, answers, contexts, ground_truths) -> list[dict]:
    """One RAGAS pass → list of {metric: float|nan} rows in input order."""
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
    from ragas.run_config import RunConfig
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    dataset = Dataset.from_dict({
        "question": questions, "answer": answers,
        "contexts": contexts, "ground_truth": ground_truths,
    })
    # Chỉ định rõ judge LLM + embeddings (default của ragas 0.1 là gpt-3.5-turbo)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=ChatOpenAI(model=RAGAS_LLM_MODEL, temperature=0),
        embeddings=OpenAIEmbeddings(model=RAGAS_EMBEDDING_MODEL),
        run_config=RunConfig(max_workers=8, timeout=120, max_retries=5),
        raise_exceptions=False,
    )
    df = result.to_pandas()
    return [{m: row.get(m) for m in METRICS} for _, row in df.iterrows()]


def evaluate_ragas(questions: list[str], answers: list[str],
                   contexts: list[list[str]], ground_truths: list[str]) -> dict:
    """Run RAGAS evaluation.

    Trả về per_question theo đúng thứ tự đầu vào và metadata.evaluator_models
    (LLM + embedding thực sự dùng). Câu bị NaN (judge parse lỗi) được chấm lại;
    nếu vẫn NaN sau RAGAS_MAX_ATTEMPTS lượt thì raise — không thay NaN bằng 0.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY chưa được cấu hình trong .env")
    if not (len(questions) == len(answers) == len(contexts) == len(ground_truths)):
        raise ValueError("questions/answers/contexts/ground_truths must have the same length")

    rows: list[dict | None] = [None] * len(questions)
    pending = list(range(len(questions)))
    for attempt in range(1, RAGAS_MAX_ATTEMPTS + 1):
        scored = _run_ragas([questions[i] for i in pending], [answers[i] for i in pending],
                            [contexts[i] for i in pending], [ground_truths[i] for i in pending])
        still_nan = []
        for i, row in zip(pending, scored):
            if all(_is_finite(row[m]) for m in METRICS):
                rows[i] = {m: float(row[m]) for m in METRICS}
            else:
                still_nan.append(i)
        pending = still_nan
        if not pending:
            break
        print(f"  ⚠️  RAGAS attempt {attempt}: {len(pending)} rows có NaN, chấm lại...")
    if pending:
        raise ValueError(f"RAGAS trả NaN cho câu (index) {pending} sau {RAGAS_MAX_ATTEMPTS} lượt")

    per_question = [
        EvalResult(question=q, answer=a, contexts=list(c), ground_truth=g, **row)
        for q, a, c, g, row in zip(questions, answers, contexts, ground_truths, rows)
    ]
    aggregate = {m: sum(getattr(r, m) for r in per_question) / len(per_question) for m in METRICS}
    return {**aggregate, "per_question": per_question,
            "metadata": {"evaluator_models": [RAGAS_LLM_MODEL, RAGAS_EMBEDDING_MODEL]}}


DIAGNOSTIC_TREE = {
    "faithfulness": ("LLM hallucinating — câu trả lời chứa thông tin không có trong context",
                     "Tighten prompt (chỉ dùng context, trích nguyên văn số liệu), lower temperature"),
    "context_recall": ("Missing relevant chunks — retriever bỏ sót tài liệu chứa đáp án",
                       "Improve chunking (child→parent), add BM25/HyQA, tăng top_k trước rerank"),
    "context_precision": ("Too many irrelevant chunks — context nhiễu hoặc chunk đúng bị xếp hạng thấp",
                          "Add reranking hoặc metadata filter (version/category), giảm top_k"),
    "answer_relevancy": ("Answer doesn't match question — trả lời lan man hoặc né câu hỏi",
                         "Improve prompt template: trả lời trực tiếp câu hỏi trước, rồi mới giải thích"),
}


def failure_analysis(eval_results: list[EvalResult], bottom_n: int = 10) -> list[dict]:
    """Analyze bottom-N worst questions using Diagnostic Tree."""
    analyzed = []
    for r in eval_results:
        scores = {m: getattr(r, m) for m in METRICS}
        avg = sum(scores.values()) / len(scores)
        worst_metric = min(scores, key=scores.get)
        diagnosis, fix = DIAGNOSTIC_TREE[worst_metric]
        analyzed.append({
            "question": r.question,
            "answer": r.answer,
            "ground_truth": r.ground_truth,
            "avg_score": round(avg, 4),
            "scores": {m: round(v, 4) for m, v in scores.items()},
            "worst_metric": worst_metric,
            "score": round(scores[worst_metric], 4),
            "diagnosis": diagnosis,
            "suggested_fix": fix,
        })
    analyzed.sort(key=lambda x: x["avg_score"])
    return analyzed[:bottom_n]


def save_report(results: dict, failures: list[dict], path: str = "reports/ragas_report.json"):
    """Save evaluation report to JSON. (Đã implement sẵn)"""
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    report = {
        "aggregate": {k: v for k, v in results.items() if k != "per_question"},
        "num_questions": len(results.get("per_question", [])),
        "failures": failures,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test questions")
    print("Run pipeline.py first to generate answers, then call evaluate_ragas().")
