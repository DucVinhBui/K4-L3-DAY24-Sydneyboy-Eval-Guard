# Nhóm thực hiện K4 Track 3B

Tên nhóm: Sydneyboy

Repo chung: https://github.com/DucVinhBui/K4-Track-3B-Day24-Eval-Guard

Trưởng nhóm/người nộp: Bùi Đức Vinh — 2A202602801

Ngày lab/deadline áp dụng: lab ngày 2026-10-12; deadline theo thông báo lớp — Asia/Ho_Chi_Minh (UTC+07:00)

Commit dùng để chấm: COMMIT_SHA_PENDING

Mỗi nhóm nộp một repo. Điền đủ thành viên và một mục INDIVIDUAL cho từng người.

## Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò / công việc thật | Bằng chứng |
|---|---|---|---|---|
| 1 | Bùi Đức Vinh | 2A202602801 | Tích hợp pipeline m1–m5, sinh 50 answers live, Phase A (`src/phase_a_ragas.py` Tasks 1–4, `src/m4_eval.py`), README | Commits của @VinhBuii; `artifacts/answers_50q.json`, `artifacts/ragas_50q.json`, `doc/reports/failure_clusters.md` |
| 2 | Đỗ Phúc Hưng | 2A202602762 | Phase B (`src/phase_b_judge.py` Tasks 5–8: pairwise prompt, swap-and-average, Cohen's κ, bias report) | Commits của @huwungG; `artifacts/judge_results.json`, `doc/reports/bias_report.md` |
| 3 | Nguyễn Anh Trí | 2A202602730 | Phase C (`src/phase_c_guard.py` Tasks 9a–12, `guardrails/config.yml`), blueprint CI/CD | Commits của @anhtri04; `artifacts/guard_results.json`, `doc/reports/blueprint.md` |

Người tích hợp/chạy batch/nộp link: Bùi Đức Vinh — cài môi trường, chạy Qdrant, sinh 50 answers và chạy
cả ba phase live trên máy của Vinh; Hưng và Trí làm việc trực tiếp trên workspace này (không có máy
riêng), commit dưới tài khoản GitHub của mỗi người. Bằng chứng: `git log --format='%an %s'`.

## Môi trường và chuẩn bị trước lớp

OS/Python/compiler: macOS 27.0 (Apple Silicon), Python 3.11.8 (Anaconda) trong `.venv`.
Virtualenv/dependencies/imports: `pip install -r requirements/requirements.txt -c requirements/constraints-core.txt`;
`pip check` → "No broken requirements found". Phải thêm `pyarrow<18` vì pyarrow mới cần NumPy ≥2 (lab pin
1.26.4). Phiên bản chính: nemoguardrails 0.10.0, presidio-analyzer/anonymizer 2.2.364, ragas 0.1.22,
openai 1.109.1, qdrant-client 1.9.2, spaCy 3.8.16 + en_core_web_lg 3.8.0 (cài từ wheel vì
`spacy download` bị treo). Offline tests: `python -m pytest tests/ -q` → 86 passed.
Models/Qdrant/50 answers đã chuẩn bị: Qdrant v1.9.7 chạy bằng `docker compose -f infra/docker-compose.yml up -d`;
BGE-M3 và bge-reranker-v2-m3 tải về local; `python scripts/setup_answers.py --live` sinh 50 answers, cả 50 ở
`generation_mode = llm` (gpt-4o-mini-2024-07-18), không có câu nào dùng `extractive_fallback`. qdrant-client
1.9 không có `query_points()` nên m2 dùng `search()` khi thiếu. NeMo 0.10 chạy runtime thật (input/output rail
gọi gpt-4o-mini), không chỉ pip resolve: bằng chứng là `artifacts/guard_results.json` với `run_kind = live`.

## INDIVIDUAL

### BuiDucVinh-2A202602801

- Phần được giao và phần thực tế đã làm: đưa pipeline Day 18 (m1–m5) vào repo, sửa m2 cho qdrant-client 1.9,
  viết adapter `src/m4_eval.py` (trả `evaluator_models`, chấm lại câu NaN tối đa 3 lượt thay vì gán 0); Phase A
  Tasks 1–4 trong `src/phase_a_ragas.py` (`group_by_distribution`, `run_ragas_50q`, `bottom_10`, `cluster_analysis`);
  sinh 50 answers và chạy Phase A live; viết `doc/reports/failure_clusters.md` và README.
- Bằng chứng: commits của @VinhBuii (feat(pipeline), feat(m4), feat(phase-a) Tasks 1–4, fix(m2), data(phase-a));
  `artifacts/answers_50q.json`, `artifacts/ragas_50q.json`.
- Cách kiểm tra: unit mock `python -m pytest tests/ -q` (86 passed); live `python scripts/run_experiments.py --phase a --live`
  (run 2026-10-12T10:20:28Z, 50 câu, không NaN); `python scripts/check_lab.py` cho schema/metadata.
- Điều đã học: điểm RAGAS thấp không đồng nghĩa với hallucination — 8/50 câu "Không tìm thấy." có faithfulness
  và answer_relevancy ≈ 0 dù context đúng (q9 có context_recall 1.0); phải đọc answer/context trước khi tin nhãn
  diagnosis tự động. Matrix đếm theo worst_metric, chọn nhóm yếu theo mean chứ không theo tổng câu.
- Giới hạn/cách xử lý: evaluator và generator cùng là gpt-4o-mini; chỉ một lần chạy 50 câu, nên chênh lệch <0.05
  giữa các distribution coi là nhiễu. Đề xuất sửa prompt generation và tăng top-k được ghi trong failure_clusters.md,
  chưa chạy lại.
- Nguồn/AI hỗ trợ nếu có: dùng Claude Code (Anthropic) để hỗ trợ viết code, chạy lệnh và soạn báo cáo; tự kiểm
  chứng bằng unit test, chạy live và đọc lại từng answer/context của bottom 10 trước khi viết kết luận.

### DoPhucHung-2A202602762

- Phần được giao và phần thực tế đã làm: Phase B trong `src/phase_b_judge.py` — prompt pairwise có reference ưu tiên
  độ chính xác, ghi rõ độ dài/vị trí không phải tiêu chí (`PAIRWISE_SYSTEM_PROMPT`, `PAIRWISE_PROMPT_TEMPLATE`);
  validate JSON (`_parse_pairwise`); `pairwise_judge` qua OpenAI JSON mode, temperature 0; `swap_and_average` quy đổi
  winner lượt 2 về A/B gốc; `cohen_kappa` tính p_o/p_e thủ công; `bias_report` đếm position/verbosity; viết
  `doc/reports/bias_report.md`.
- Bằng chứng: commits của @huwungG (feat(phase-b) Tasks 5–8, data(phase-b), docs(bias)); `artifacts/judge_results.json`.
- Cách kiểm tra: unit mock `python -m pytest tests/ -q`; live `python scripts/run_experiments.py --phase b --live`
  (run 2026-10-12T10:18:49Z): 5 cặp, position bias 2/5, verbosity 0.667 trên 3 case decisive, κ = 1.0 trên 10 nhãn.
- Điều đã học: judge một lượt không đáng tin — q5 (cả hai answer đều sai) đổi winner theo vị trí, nên bắt buộc
  swap-and-average và coi cặp không nhất quán là tie. Verbosity rate cao chưa chứng minh bias: winner dài hơn ở q1/q41
  cũng là answer đúng hơn. Cohen's κ cần tính chance agreement, không chỉ % trùng.
- Giới hạn/cách xử lý: chỉ 5 cặp và 10 nhãn; judge cùng họ với generator; reasoning có lúc không khớp answer (q12).
  Đề xuất thêm quy tắc "cả hai sai → tie" và mở rộng nhãn human, ghi trong bias_report.md.
- Nguồn/AI hỗ trợ nếu có: dùng Claude Code (Anthropic) trên workspace chung để hỗ trợ viết code và báo cáo; tự kiểm
  chứng bằng cách đọc lại reasoning hai lượt của từng cặp và tính lại κ bằng tay (p_o = 1.00, p_e = 0.52).

## Cập nhật sau khi nộp

{{Ghi phiên bản nộp; nếu sửa sau deadline, ghi commit/thời điểm/lý do và thông báo
coach cho phép áp dụng bản cập nhật. Nếu không có cập nhật, ghi rõ không có.}}
