# Phân tích lỗi Phase A

Nhóm: Sydneyboy

Người phụ trách: Bùi Đức Vinh — 2A202602801

Nguồn: `artifacts/ragas_50q.json`; run timestamp: 2026-10-12T10:20:28Z.
Generation mode/fallback và điều kiện chạy: `run_kind = live`; 50/50 answers sinh ở chế độ `llm`
(không có câu nào rơi về fallback extractive), pipeline Day 18 đầy đủ: 107 chunks hierarchical,
BM25 (underthesea) + BGE-M3 dense trên Qdrant v1.9.7 → RRF → bge-reranker-v2-m3 lấy top-3 →
gpt-4o-mini sinh câu trả lời, có context enrichment (m5) prepend vào mỗi chunk.
Models generation/evaluator: generation `gpt-4o-mini-2024-07-18`; evaluator `gpt-4o-mini`
(temperature 0) + `text-embedding-3-small`, RAGAS 0.1.22 qua adapter `src/m4_eval.py`.
Không câu nào bị NaN sau tối đa 3 lượt chấm lại, nên không có điểm nào bị gán 0 thay cho NaN.

## Điểm theo distribution

| Metric | factual (20) | multi_hop (20) | adversarial (10) |
|---|---|---|---|
| faithfulness | 0.812 | 0.489 | 0.900 |
| answer_relevancy | 0.489 | 0.402 | 0.526 |
| context_precision | 0.950 | 0.929 | 0.900 |
| context_recall | 0.800 | 0.767 | 0.683 |
| avg_score | 0.763 | 0.647 | 0.752 |

Retrieval (precision/recall) tốt hơn generation một cách rõ rệt ở cả ba nhóm: context_precision
≥0.90 nhưng answer_relevancy chỉ 0.40–0.53. Multi_hop kéo faithfulness xuống thấp nhất (0.489).

## Bottom 10 và nguyên nhân

| Rank | id | Question | Distribution | avg_score | worst_metric | Diagnosis | Suggested fix |
|---|---|---|---|---|---|---|---|
| 1 | 39 | So sánh yêu cầu mật khẩu giữa policy v1.0 và v2.0 về độ dài tối thiểu, thời hạn đổi và MFA. | multi_hop | 0.0000 | faithfulness | LLM hallucinating (faithfulness=0.00; cần ghép ≥2 tài liệu — top-3 sau rerank dễ thiếu một nửa thông tin) | Tighten system prompt, lower temperature |
| 2 | 5 | Muốn mua thiết bị trị giá 55 triệu cần ai phê duyệt? | factual | 0.2500 | faithfulness | LLM hallucinating (faithfulness=0.00; câu một tài liệu — kiểm tra chunk chứa con số có lọt top-3 không) | Tighten system prompt, lower temperature |
| 3 | 6 | Thông tin lương thuộc cấp độ phân loại dữ liệu nào? | factual | 0.3333 | faithfulness | LLM hallucinating (faithfulness=0.00; câu một tài liệu — kiểm tra chunk chứa con số có lọt top-3 không) | Tighten system prompt, lower temperature |
| 4 | 22 | Nếu cần mua một chiếc laptop 30 triệu cho nhân viên mới, ai phê duyệt và cần gì từ phòng CNTT? | multi_hop | 0.3333 | faithfulness | LLM hallucinating (faithfulness=0.00; cần ghép ≥2 tài liệu — top-3 sau rerank dễ thiếu một nửa thông tin) | Tighten system prompt, lower temperature |
| 5 | 50 | Nhân viên Manager có thể dùng VPN cá nhân (như NordVPN) khi WFH để tăng bảo mật thêm không? | adversarial | 0.3333 | faithfulness | LLM hallucinating (faithfulness=0.00; bẫy phiên bản/phủ định — kiểm tra context có lẫn chính sách cũ (v2023, v1)) | Tighten system prompt, lower temperature |
| 6 | 33 | Nhân viên Manager có thâm niên 12 năm: tổng phụ cấp hàng tháng và số ngày phép năm theo v2024 là bao nhiêu? | multi_hop | 0.3750 | faithfulness | LLM hallucinating (faithfulness=0.00; cần ghép ≥2 tài liệu — top-3 sau rerank dễ thiếu một nửa thông tin) | Tighten system prompt, lower temperature |
| 7 | 30 | So sánh quyền lợi bảo hiểm giữa nhân viên thử việc và nhân viên chính thức. | multi_hop | 0.4750 | answer_relevancy | Answer doesn't match question (answer_relevancy=0.00; cần ghép ≥2 tài liệu — top-3 sau rerank dễ thiếu một nửa thông tin) | Improve prompt template |
| 8 | 9 | Nam nhân viên được nghỉ bao nhiêu ngày khi vợ sinh con? | factual | 0.5000 | faithfulness | LLM hallucinating (faithfulness=0.00; câu một tài liệu — kiểm tra chunk chứa con số có lọt top-3 không) | Tighten system prompt, lower temperature |
| 9 | 21 | Một nhân viên Senior có 9 năm thâm niên được nghỉ bao nhiêu ngày phép năm và lương trong khoảng nào? | multi_hop | 0.5625 | answer_relevancy | Answer doesn't match question (answer_relevancy=0.00; cần ghép ≥2 tài liệu — top-3 sau rerank dễ thiếu một nửa thông tin) | Improve prompt template |
| 10 | 31 | Nhân viên đi công tác trong nước, ở khách sạn 2 đêm với giá 1.500.000 VNĐ/đêm. Công ty thanh toán tối đa bao nhiêu cho tiền khách sạn? | multi_hop | 0.6155 | faithfulness | LLM hallucinating (faithfulness=0.25; cần ghép ≥2 tài liệu — top-3 sau rerank dễ thiếu một nửa thông tin) | Tighten system prompt, lower temperature |

Diagnosis trên do `bottom_10()` của nhóm sinh theo worst_metric và distribution. Đọc lại
answer/contexts/reference cho thấy nhãn "hallucinating" **không đúng nguyên nhân** cho phần lớn
các câu này, nên bên dưới là chẩn đoán đã kiểm chứng bằng tay.

**Nhóm lỗi 1 — từ chối quá mức ("Không tìm thấy.").** 8/50 answer là đúng chuỗi
"Không tìm thấy." (ids 5, 6, 9, 22, 33, 39, 48, 50), và 7 trong số đó nằm trong bottom 10.
RAGAS chấm câu từ chối có faithfulness 0 (không có claim nào để kiểm chứng) và
answer_relevancy 0 (không trả lời câu hỏi), nên đây là lỗi **generation**, không phải bịa thông tin.

| Nhóm | n | faithfulness | answer_relevancy | context_precision | context_recall |
|---|---|---|---|---|---|
| Answer = "Không tìm thấy." | 8 | 0.125 | 0.000 | 0.854 | 0.417 |
| Các answer còn lại | 42 | 0.810 | 0.549 | 0.946 | 0.829 |

Bằng chứng rõ nhất là q9: context_precision = 1.0 và context_recall = 1.0, chunk thứ hai
trong top-3 (chính sách nghỉ phép đặc biệt v1.1) có dòng "Sinh con (nam giới): 5 ngày", nhưng
model vẫn trả "Không tìm thấy.". Retrieval đúng, model từ chối do system prompt quá chặt
("Nếu không có → nói 'Không tìm thấy.'") cộng với dòng enrichment đứng đầu mỗi chunk làm thông
tin chính bị đẩy xa. q39 là trường hợp có một phần dữ liệu: top-3 chứa v1.0 "tối thiểu 8 ký tự"
và v2.0 "đổi mỗi 120 ngày" + phương thức MFA, nhưng thiếu độ dài 12 ký tự của v2.0 và chu kỳ 90 ngày
của v1.0. Model từ chối toàn bộ thay vì so sánh phần đã có. RAGAS chấm context_precision = 0 cho q39
dù 3 chunk đều đúng chủ đề — điểm bất thường của evaluator khi answer là câu từ chối, nên không dùng
riêng q39 để kết luận retrieval hỏng.

**Nhóm lỗi 2 — trả lời một nửa (multi_hop).** q21 trả đúng 18 ngày phép (15 + 3) nhưng nói
lương "không có thông tin cụ thể"; q30 nêu đúng quyền lợi của nhân viên thử việc nhưng bảo
nhân viên chính thức "không được đề cập". Context_recall chỉ 0.5 ở cả hai: top-3 chứa một
tài liệu, thiếu tài liệu thứ hai (bảng lương P3–P4, gói PVI). Model nói "không có thông tin" cho
nửa còn lại, câu trả lời mang tính noncommittal nên answer_relevancy = 0.

**Nhóm lỗi 3 — tính toán đúng nhưng claim không có trong context.** q31 ra đúng
2 × 1.200.000 = 2.400.000 VNĐ, khớp reference, nhưng faithfulness 0.25 vì phép nhân và tổng
là claim suy luận, không xuất hiện nguyên văn trong context. Đây là giới hạn của metric
faithfulness với câu hỏi cần tính toán, không phải lỗi model.

## Matrix và nhóm yếu nhất

Mỗi câu được đếm đúng một lần, theo worst_metric của nó (kể cả câu có điểm cao); đây là
phân bố metric yếu nhất, không phải số failure.

| worst_metric | factual | multi_hop | adversarial | Tổng |
|---|---|---|---|---|
| faithfulness | 5 | 10 | 1 | 16 |
| answer_relevancy | 12 | 10 | 5 | 27 |
| context_precision | 1 | 0 | 1 | 2 |
| context_recall | 2 | 0 | 3 | 5 |
| Tổng | 20 | 20 | 10 | 50 |

Nhóm yếu theo mean thấp nhất: multi_hop; mean: 0.6467.
Worst metric xuất hiện nhiều nhất: answer_relevancy; số câu: 27.

Multi_hop yếu vì cần ghép ≥2 tài liệu nhưng pipeline chỉ đưa top-3 chunk sau rerank vào
prompt: khi hai chunk cùng thuộc một tài liệu, nửa thông tin còn lại bị thiếu (q21, q30), và
model chọn từ chối toàn bộ (q22, q33, q39) thay vì trả lời phần đã có. 10/20 câu multi_hop có
worst_metric là faithfulness, phần lớn do câu từ chối hoặc phép tính suy luận như q31.
Answer_relevancy là worst_metric phổ biến nhất ở cả ba nhóm vì RAGAS sinh câu hỏi ngược từ
answer: answer ngắn, có câu rào đón hoặc nhắc thêm chính sách cũ thì cosine với câu hỏi gốc thấp.

Đề xuất sửa và cách kiểm chứng:

1. Bỏ quy tắc "chỉ nói 'Không tìm thấy.'"; yêu cầu trả lời phần có trong context và nói rõ phần
   nào thiếu. Chạy lại 8 câu từ chối (5, 6, 9, 22, 33, 39, 48, 50); kỳ vọng faithfulness và
   answer_relevancy của nhóm này tăng từ 0.125/0.000.
2. Với multi_hop, tăng số chunk vào prompt từ 3 lên 5 hoặc đa dạng hoá theo `source` (tối đa
   2 chunk mỗi tài liệu). Đo lại context_recall multi_hop (hiện 0.767) và avg_score (0.647).
3. Đặt dòng enrichment sau nội dung chunk (hoặc chỉ dùng khi index) để con số quy định nằm
   đầu context. Kiểm tra q9 phải trả đúng 5 ngày.
4. Sau mỗi thay đổi, chạy `python scripts/setup_answers.py --live` rồi
   `python scripts/run_experiments.py --phase a --live`, so sánh bảng distribution và matrix
   với run 2026-10-12T10:20:28Z; chỉ giữ thay đổi nếu multi_hop tăng mà factual không giảm.

## Bẫy adversarial và giới hạn

Adversarial (0.752) thấp hơn factual (0.763) nhưng cao hơn multi_hop (0.647). Khoảng cách với
factual chỉ 0.011, nên không thể kết luận pipeline "bị bẫy" hay "nhận ra bẫy" chỉ từ điểm mean.
Đọc từng answer adversarial:

- **Version conflict được xử lý đúng ở phần lớn câu:** q41 trả 15 ngày (v2024, không phải 12 của
  v2023), q43 trả 12 ký tự (v2.0, không phải 8 của v1.0), q45 nói MFA bắt buộc (v2.0). Faithfulness 1.0
  nhưng answer_relevancy chỉ 0.51–0.68 vì answer ngắn, không nhắc lý do bản cũ bị thay.
- **q49 nêu chính sách cũ trước:** answer mở đầu bằng "theo chính sách cũ (v2023) … 12 ngày" rồi chỉ
  nói bản 2024 đang hiệu lực mà không nêu con số 15 ngày. Context_recall 0.67, rủi ro người đọc lấy nhầm
  con số cũ dù faithfulness = 1.0.
- **q50 (phủ định/mâu thuẫn chính sách) nằm trong bottom 10:** reference là "KHÔNG, chính sách VPN cấm
  VPN cá nhân". Chunk top-1 có nguyên văn quy định "Không sử dụng VPN cá nhân (NordVPN, ExpressVPN)
  trong mạng công ty", nhưng model trả "Không tìm thấy.". Câu hỏi viết theo dạng gợi ý ("để tăng bảo
  mật thêm") khiến model không nhận ra quy định cấm chính là câu trả lời. Không sai về an toàn nhưng bỏ
  lỡ câu phủ định có sẵn trong context — cùng cơ chế từ chối quá mức ở nhóm lỗi 1.
- Context_recall adversarial thấp nhất (0.683) và là worst_metric của 3/10 câu: rerank top-3 thường lấy cả
  bản cũ lẫn bản mới, chiếm chỗ của đoạn giải thích cần cho reference.

Giới hạn: chỉ 50 câu (10 adversarial) và một lần chạy; evaluator cũng là gpt-4o-mini (cùng họ với
generator) nên có thể thiên vị cách diễn đạt của chính nó; RAGAS chấm câu từ chối bằng 0 dù câu từ chối
an toàn trong một số trường hợp; answer_relevancy phụ thuộc embedding `text-embedding-3-small` trên tiếng
Việt. Mọi chênh lệch dưới ~0.05 giữa các distribution nên coi là nhiễu cho đến khi chạy lặp nhiều lần.
