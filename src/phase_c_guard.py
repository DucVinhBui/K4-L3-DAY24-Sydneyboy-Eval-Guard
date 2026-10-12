from __future__ import annotations

"""Phase C: Production Guardrails — Presidio PII + NeMo Guardrails + P95 Latency."""

import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ADVERSARIAL_SET_PATH, GUARDRAILS_CONFIG_DIR, LATENCY_BUDGET_P95_MS, PRESIDIO_LANGUAGE


# ─── Task 9a: Presidio PII Detection ─────────────────────────────────────────

def setup_presidio():
    """Khởi tạo Presidio engine với custom Vietnamese PII recognizers. (Đã implement sẵn)

    Custom recognizers thêm vào:
        VN_CCCD  — số CCCD 12 chữ số hoặc CMND 9 chữ số
        VN_PHONE — số điện thoại Việt Nam (0[3-9]xxxxxxxx)

    Các recognizers mặc định đã có sẵn: EMAIL, PHONE_NUMBER (international), ...
    """
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
    from presidio_anonymizer import AnonymizerEngine

    cccd_recognizer = PatternRecognizer(
        supported_entity="VN_CCCD",
        patterns=[
            Pattern("CCCD 12 digits", r"\b\d{12}\b", 0.9),
            Pattern("CMND 9 digits",  r"\b\d{9}\b",  0.7),
        ],
    )
    phone_recognizer = PatternRecognizer(
        supported_entity="VN_PHONE",
        patterns=[Pattern("VN mobile", r"\b0[3-9]\d{8}\b", 0.9)],
    )

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers()
    registry.add_recognizer(cccd_recognizer)
    registry.add_recognizer(phone_recognizer)

    analyzer  = AnalyzerEngine(registry=registry)
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


# Chỉ chặn các loại định danh mà task yêu cầu. NER mặc định của spaCy "en"
# (PERSON/LOCATION/DATE_TIME/NRP) đoán sai nhiều trên câu tiếng Việt sạch nên
# không dùng làm tín hiệu block — nếu dùng sẽ gây false positive cho clean set.
PII_ENTITIES = frozenset({
    "VN_CCCD", "VN_PHONE", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE",
})
PII_MIN_SCORE = 0.4


def pii_scan(text: str, analyzer=None, anonymizer=None) -> dict:
    """Task 9a: Quét PII trong văn bản bằng Presidio.

    Returns:
        {
          "has_pii":    bool,
          "entities":   [{"type": str, "text": str, "score": float, "start": int, "end": int}],
          "anonymized": str,   # text với PII được thay bằng <TYPE>
        }
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()

    findings = [r for r in analyzer.analyze(text=text, language=PRESIDIO_LANGUAGE)
                if r.entity_type in PII_ENTITIES and r.score >= PII_MIN_SCORE]
    if not findings:
        return {"has_pii": False, "entities": [], "anonymized": text}

    anonymized = anonymizer.anonymize(text=text, analyzer_results=findings).text
    entities = [
        {"type": r.entity_type, "text": text[r.start:r.end],
         "score": round(float(r.score), 3), "start": r.start, "end": r.end}
        for r in sorted(findings, key=lambda r: (r.start, -r.score))
    ]
    return {"has_pii": True, "entities": entities, "anonymized": anonymized}


# ─── Task 9b + 11: NeMo Guardrails ───────────────────────────────────────────

def setup_nemo_rails():
    """Khởi tạo NeMo Guardrails từ guardrails/config.yml. (Đã implement sẵn)

    Config directory: guardrails/
        config.yml  — model + rails config
        rails.co    — câu từ chối Colang 1.0; built-in self-check flows được bật trong YAML
    """
    from nemoguardrails import RailsConfig, LLMRails
    config = RailsConfig.from_path(GUARDRAILS_CONFIG_DIR)
    rails  = LLMRails(config)
    return rails


def _rail_stopped(result) -> bool:
    """Quyết định block lấy từ log của NeMo (rail nào đã dừng flow), không đoán từ text."""
    activated = getattr(getattr(result, "log", None), "activated_rails", None)
    if activated is None:
        raise ValueError("NeMo result has no activated_rails log; pass options.log.activated_rails")
    return any(getattr(rail, "stop", False) for rail in activated)


def _response_text(result) -> str:
    response = result.response
    if isinstance(response, list):
        return response[-1].get("content", "") if response else ""
    return str(response or "")


async def check_input_rail(text: str, rails=None) -> dict:
    """Task 9b: Kiểm tra input qua NeMo input rails (topic guard + jailbreak guard).

    Returns:
        {
          "allowed":        bool,
          "blocked_reason": str | None,
          "response":       str,          # NeMo's raw response
        }
    """
    if rails is None:
        rails = setup_nemo_rails()
    result = await rails.generate_async(
        messages=[{"role": "user", "content": text}],
        options={"rails": ["input"], "log": {"activated_rails": True}},
    )
    blocked = _rail_stopped(result)
    return {
        "allowed": not blocked,
        "blocked_reason": "nemo_input_rail" if blocked else None,
        "response": _response_text(result),
    }


async def check_output_rail(question: str, answer: str, rails=None) -> dict:
    """Task 11: Kiểm tra LLM output qua NeMo output rails trước khi trả về user.

    NeMo output rails hoạt động trong context của cả cuộc hội thoại (input + output).
    Kiểm tra PII và nội dung nhạy cảm. Self-check này không thay RAGAS faithfulness
    hoặc kiểm tra factual accuracy với retrieved contexts.

    Returns:
        {
          "safe":           bool,
          "flagged_reason": str | None,
          "final_answer":   str,          # answer đã qua guard (có thể bị redact)
        }
    """
    if rails is None:
        rails = setup_nemo_rails()
    # Answer có sẵn được đưa vào như lượt assistant; chỉ chạy output rail trên nó.
    result = await rails.generate_async(
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        options={"rails": ["output"], "log": {"activated_rails": True}},
    )
    flagged = _rail_stopped(result)
    return {
        "safe": not flagged,
        "flagged_reason": "nemo_output_rail" if flagged else None,
        # Answer sạch giữ nguyên; answer bị chặn được thay bằng câu từ chối của rail.
        "final_answer": _response_text(result) if flagged else answer,
    }


# ─── Task 10: Adversarial Test Suite ─────────────────────────────────────────

def run_adversarial_suite(adversarial_set: list[dict], rails=None,
                           analyzer=None, anonymizer=None) -> list[dict]:
    """Task 10: Chạy inputs qua full input guard stack, so sánh với expected.

    Guard stack order (giống request thật, dừng sớm khi đã bị chặn):
        1. pii_scan()         → block nếu has_pii
        2. check_input_rail() → block nếu jailbreak / off-topic / prompt injection
    `expected` chỉ dùng để chấm passed, không ảnh hưởng quyết định actual.
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()
    if rails is None:
        rails = setup_nemo_rails()

    async def _run_all() -> list[dict]:
        rows = []
        for item in adversarial_set:
            blocked_by = None
            if pii_scan(item["input"], analyzer, anonymizer)["has_pii"]:
                blocked_by = "presidio"
            else:
                rail = await check_input_rail(item["input"], rails)
                if not rail["allowed"]:
                    blocked_by = "nemo_input"
            actual = "blocked" if blocked_by else "allowed"
            rows.append({
                "id": item["id"],
                "category": item["category"],
                "input": item["input"],
                "expected": item["expected"],
                "actual": actual,
                "blocked_by": blocked_by,
                "passed": actual == item["expected"],
            })
        return rows

    rows = asyncio.run(_run_all())  # một event loop cho cả batch
    passed = sum(r["passed"] for r in rows)
    print(f"Input guard suite: {passed}/{len(rows)} passed")
    return rows


def measure_p95_latency(test_inputs: list[str], n_runs: int = 20,
                         rails=None, analyzer=None, anonymizer=None) -> dict:
    """Task 12: measure INPUT layers sequentially, not end-to-end guard/RAG latency.

    Reuse engines. Inside ONE event loop, execute two real warm-up calls per layer,
    excluded from samples. Then collect exactly n_runs timed samples (cycle clean
    inputs), always measuring BOTH PII and NeMo input even if PII blocks.
    Use perf_counter; keep raw milliseconds. summarize_latency() supplies linear
    percentiles at (n - 1) * q. Submission requires n_runs >= 20.
    Short-circuit request timing, RAG and output timing are outside this scope.
    """
    # TODO: Implement sample collection (the statistics helper is provided).
    # from src.experiment_support import summarize_latency
    # if not test_inputs or n_runs < 1:
    #     raise ValueError("Need inputs and n_runs >= 1")
    # if analyzer is None or anonymizer is None:
    #     analyzer, anonymizer = setup_presidio()
    # if rails is None:
    #     rails = setup_nemo_rails()
    # async def _measure():
    #     for i in range(2):
    #         text = test_inputs[i % len(test_inputs)]
    #         pii_scan(text, analyzer, anonymizer)
    #         await check_input_rail(text, rails)
    #     samples = []
    #     for i in range(n_runs):
    #         text = test_inputs[i % len(test_inputs)]
    #         t0 = time.perf_counter()
    #         pii_scan(text, analyzer, anonymizer)
    #         pii_ms = (time.perf_counter() - t0) * 1000
    #         t1 = time.perf_counter()
    #         await check_input_rail(text, rails)
    #         nemo_ms = (time.perf_counter() - t1) * 1000
    #         samples.append({"presidio_ms": pii_ms, "nemo_input_ms": nemo_ms,
    #                         "input_guard_ms": pii_ms + nemo_ms})
    #     return samples
    # return summarize_latency(asyncio.run(_measure()), warmup_runs=2)
    return {
        "scope": "input_layers_sequential", "percentile_method": "linear",
        "n_samples": 0, "warmup_runs": 0, "samples": [],
        "presidio_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
        "nemo_input_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
        "input_guard_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
        "latency_budget_ok": False, "budget_ms": LATENCY_BUDGET_P95_MS,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from scripts.run_experiments import main
    raise SystemExit(main(["--phase", "c", *sys.argv[1:]]))
