# Blueprint CI/CD cho RAG và guardrails

Nhóm: Sydneyboy

Người phụ trách: Nguyễn Anh Trí — 2A202602730

Đây là **đề xuất CI/CD**, không phải workflow đã được triển khai/chạy.
Nguồn kết quả: artifacts/ragas_50q.json, judge_results.json, guard_results.json.
Run timestamp: 2026-10-12T10:35:46Z; guard models: `gpt-4o-mini` (NeMo Guardrails 0.10 self-check, temperature 0).
Models generation/evaluator/judge từ A/B: generation `gpt-4o-mini-2024-07-18` (ragas_50q.json và
judge_results.json); evaluator `gpt-4o-mini` + `text-embedding-3-small` (ragas_50q.json, run
2026-10-12T10:20:28Z); judge `gpt-4o-mini` (judge_results.json, run 2026-10-12T10:18:49Z).

## Kiến trúc và failure action

Input → Presidio → NeMo input → RAG → NeMo output → response.
Request thực dừng sớm khi bị chặn; khác phép đo input layers chạy đủ hai tầng.

| Tầng | Kiểm tra | Khi phát hiện | Log |
|---|---|---|---|
| Presidio (`pii_scan`) | VN_CCCD, VN_PHONE, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, IBAN_CODE, score ≥0.4 | Dừng request, trả lời từ chối, không gọi LLM nào | Chỉ log loại entity + vị trí span và text đã redact, không log giá trị gốc |
| NeMo input (`check_input_rail`) | self_check_input: off-topic, jailbreak, giả danh vai trò, trích xuất prompt/context, dữ liệu cá nhân người khác, credential thật | Dừng request, trả refusal của rail | Log `activated_rails[*].stop` và tên rail |
| RAG (m1–m5) | Hybrid search → rerank top-3 → gpt-4o-mini | Không có context đủ → nói rõ phần thiếu | Log question_id, ids chunk, latency |
| NeMo output (`check_output_rail`) | self_check_output: lộ PII, mật khẩu, thông tin nội bộ bí mật | Thay answer bằng refusal; answer an toàn giữ nguyên | Log `flagged_reason = nemo_output_rail`, không log answer gốc bị chặn |

Quyết định block lấy từ `result.log.activated_rails[*].stop` của NeMo, không đoán theo chữ "xin lỗi".
Output case thật: #201 và #202 (an toàn, có email helpdesk công khai) được giữ nguyên; #203 (lộ số CCCD)
và #204 (lộ mật khẩu admin) bị thay bằng refusal — 4/4 đúng.

Secrets: `OPENAI_API_KEY` chỉ nằm trong `.env` (đã gitignore) ở local; trong CI đề xuất lưu ở
repository secret và inject qua env, không in ra log. Fallback: nếu NeMo/OpenAI lỗi hoặc timeout, input
rail **fail-closed** (từ chối kèm thông báo thử lại) thay vì cho qua; Presidio chạy local nên vẫn chặn
được PII khi API lỗi. Fallback generation `extractive_fallback` (trả chunk đầu, không LLM) chỉ dùng cho dev, và
artifact ghi rõ `generation_mode` từng câu để không lẫn với run live (run này 50/50 là `llm`).

## Phạm vi và số đo latency

Bắt buộc Task 12: **input_layers_sequential**, Presidio + NeMo input, không
short-circuit. Engines tạo trước đo; có hai warm-up thật không tính vào mẫu.
Percentile nội suy tuyến tính từ raw samples; tổng từ tổng từng sample.

Số mẫu timed: 20; warm-up: 2;
phương pháp: linear (nội suy tuyến tính trên raw samples, `time.perf_counter`).

| Layer / scope | P50 ms | P95 ms | P99 ms | Tình trạng |
|---|---|---|---|---|
| Presidio | 9.04 | 10.95 | 11.25 | Đã đo Task 12, rất nhanh (local) |
| NeMo input | 727.12 | 885.09 | 959.05 | Đã đo Task 12, chiếm ~99% thời gian |
| Input guard sequential | 736.42 | 893.53 | 967.98 | Đã đo Task 12, vượt target 500ms |
| RAG | chưa đo | chưa đo | chưa đo | Ngoài phạm vi bắt buộc |
| NeMo output | chưa đo | chưa đo | chưa đo | Ngoài phạm vi bắt buộc |
| Full guard / short-circuit request | chưa đo | chưa đo | chưa đo | Không suy từ input_guard_ms |

Input-layer budget target: 500ms; kết quả thực tế/budget_ok: P95 893.53ms, `latency_budget_ok = false`.
Bottleneck là NeMo input: mỗi lần kiểm tra là một lượt gọi gpt-4o-mini qua mạng (P50 727ms), còn
Presidio chỉ ~9ms. Hướng giảm: cache quyết định cho câu hỏi lặp lại, dùng classifier nhỏ chạy local
(hoặc embedding similarity với tập jailbreak đã biết) để chỉ gọi LLM với câu không chắc chắn, hoặc
chạy NeMo input song song với retrieval và huỷ RAG nếu bị chặn.

Lịch sử chạy: run 1 (prompt self-check gốc) NeMo input P95 790.8ms, input guard P95 799.8ms; run cuối
(prompt chi tiết hơn, temperature 0) P95 885.09/893.53ms. Prompt dài hơn làm tăng ~95ms ở P95, đổi lại
sửa được 3 lỗi phân loại (xem phần Monitoring).

Kế hoạch đo phần chưa đo: chạy end-to-end 50 câu test set + 20 attacks với 2 warm-up, ghi timestamp
`t_presidio`, `t_nemo_in`, `t_rag`, `t_nemo_out` cho mỗi request; báo P50/P95/P99 riêng cho request
bị chặn sớm và request đi hết luồng, không cộng percentile của từng tầng.

## CI gates đề xuất

- RAGAS faithfulness ≥0.75, avg_score ≥0.65 trên 50 câu.
- Attacks ≥18/20 cho CI đề xuất; clean 8/8 allowed; output cases đúng.
- Full guard P95 <500ms chỉ áp dụng sau khi thực sự đo full guard.

Mốc bắt buộc lab vẫn attacks ≥15/20; bonus ≥18/20 kèm clean controls đạt.
{{Đề xuất lệnh job và cách script trả nonzero khi không đạt. MIN_* là biến đề
xuất, không tự làm quality gate nếu runner chưa kiểm tra ngưỡng. Ghi rõ workflow
chưa triển khai, hoặc dẫn bằng chứng nếu nhóm thực sự đã triển khai.}}

## Monitoring và cải tiến

{{Nêu metric, ngưỡng cảnh báo, cách lấy samples, xử lý false positives, drift,
privacy và người xử lý. Dùng kết quả thật và ghi giới hạn của bộ 50/20/8/4.}}

RAGAS mean/worst distribution: {{giá trị}}.
Cohen’s κ: {{giá trị}}.
Attacks passed: {{số lượng}}/20; clean false_positive_rate: {{giá trị}}.
{{Nêu 3–5 câu cải tiến có thể kiểm tra, gắn với bằng chứng của nhóm.}}
