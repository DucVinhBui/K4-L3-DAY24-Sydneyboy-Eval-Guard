# K4 Track 3B — Production Eval + Guardrail Stack (Day 24)

Bài nhóm đánh giá pipeline RAG chính sách nhân sự (Day 18), kiểm tra độ tin cậy
của LLM Judge và xây guardrail cho input/output.

| Thành viên | GitHub | Phụ trách |
|---|---|---|
| Bùi Đức Vinh (trưởng nhóm) | [@VinhBuii](https://github.com/VinhBuii) | Tích hợp m1–m5, sinh 50 answers, Phase A, README |
| {{Họ tên huwungG}} | [@huwungG](https://github.com/huwungG) | Phase B: pairwise judge, swap, κ, bias report |
| {{Họ tên anhtri04}} | [@anhtri04](https://github.com/anhtri04) | Phase C: Presidio, NeMo rails, latency, blueprint |

Chi tiết đóng góp từng người: [doc/TEAM.md](doc/TEAM.md). Đề bài gốc:
[doc/ASSIGNMENT.md](doc/ASSIGNMENT.md), rubric: [doc/RUBRIC.md](doc/RUBRIC.md).

## Kiến trúc

```text
User input ─► Presidio PII (CCCD/CMND, SĐT VN, email) ─► NeMo self-check input
          ─► RAG (BM25 + BGE-M3 dense → RRF → bge-reranker-v2-m3 top-3 → gpt-4o-mini)
          ─► NeMo self-check output ─► response
```

Đánh giá chạy ngoài luồng request:

- **Phase A** — RAGAS 4 metric (faithfulness, answer_relevancy, context_precision,
  context_recall) trên 50 câu (20 factual / 20 multi_hop / 10 adversarial),
  bottom-10 có chẩn đoán, matrix worst_metric × distribution.
- **Phase B** — pairwise judge có reference, chạy 2 lượt đổi vị trí A/B
  (swap-and-average), 10 nhãn nhị phân trên `model_answer` gốc → Cohen's κ với nhãn người.
- **Phase C** — 20 attacks + 8 câu sạch qua Presidio → NeMo input, 4 output case
  qua NeMo output, đo latency input layers (2 warm-up thật + ≥20 mẫu, percentile tuyến tính).

## Cấu trúc mã

| File | Nội dung |
|---|---|
| `src/m1_chunking.py` … `src/m5_enrichment.py` | Pipeline RAG Day 18 (hierarchical chunking, hybrid search, rerank, RAGAS, enrichment) |
| `src/m4_eval.py` | Adapter RAGAS: trả `metadata.evaluator_models`, chấm lại câu bị NaN thay vì gán 0 |
| `src/phase_a_ragas.py` | Tasks 1–4: group, run RAGAS, bottom-10, cluster analysis |
| `src/phase_b_judge.py` | Tasks 5–8: pairwise judge, swap-and-average, Cohen's κ, bias report |
| `src/phase_c_guard.py` | Tasks 9a–12: PII scan, input/output rail, adversarial suite, P95 latency |
| `guardrails/` | Cấu hình NeMo 0.10 (Colang 1.0, self-check prompts) |
| `artifacts/` | JSON kết quả thật; `doc/reports/` báo cáo phân tích |

Một số quyết định thiết kế:

- **PII chỉ chặn theo loại định danh** (`VN_CCCD`, `VN_PHONE`, `EMAIL_ADDRESS`,
  `PHONE_NUMBER`, `CREDIT_CARD`, `IBAN_CODE`). NER tiếng Anh của spaCy gắn nhãn
  PERSON/LOCATION sai trên câu tiếng Việt, nếu dùng sẽ chặn nhầm clean controls.
- **Quyết định block đọc từ `result.log.activated_rails[*].stop`** của NeMo,
  không đoán từ chữ "xin lỗi/không thể" (clean input #102 chứa đúng cụm này).
- **Pairwise prompt ưu tiên độ chính xác theo reference**, ghi rõ độ dài và vị
  trí không phải tiêu chí; JSON được validate (winner, reasoning, scores ∈ [0,1]).
- **m4 không thay NaN bằng 0**: chấm lại tối đa 3 lượt, vẫn NaN thì báo lỗi.

## Chạy lại

Python 3.11, Docker. Từ gốc repo:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements/requirements.txt -c requirements/constraints-core.txt
python -m spacy download en_core_web_lg
cp .env.example .env   # điền OPENAI_API_KEY
docker compose -f infra/docker-compose.yml up -d
```

Tests offline (không gọi API, không cần model):

```bash
python -m pytest tests/ -q
```

Thực nghiệm thật (gọi OpenAI, có chi phí):

```bash
python scripts/setup_answers.py --live
python scripts/run_experiments.py --phase a --live
python scripts/run_experiments.py --phase b --live
python scripts/run_experiments.py --phase c --live --latency-samples 20
python scripts/check_lab.py
```

## Kết quả

Chưa có — các artifact được sinh khi chạy thực nghiệm thật ở trên; số liệu sẽ
được cập nhật ở đây và trong `doc/reports/` từ `artifacts/*.json`.
