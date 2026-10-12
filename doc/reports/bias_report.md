# Đánh giá LLM Judge Phase B

Nhóm: Sydneyboy

Người phụ trách: Đỗ Phúc Hưng — 2A202602762

Nguồn: `artifacts/judge_results.json`; run timestamp: 2026-10-12T10:18:49Z.
Models generation/judge: generation `gpt-4o-mini-2024-07-18` (answer A từ pipeline);
judge `gpt-4o-mini`, temperature 0, `response_format = json_object`, prompt trong
`src/phase_b_judge.py` (`PAIRWISE_SYSTEM_PROMPT`, `PAIRWISE_PROMPT_TEMPLATE`).

## Năm cặp A/B và hai lượt

Nguồn cố định: A từ artifacts/answers_50q.json:answer; B từ
fixtures/human_labels_10q.json:model_answer; reference từ fixtures/test_set_50q.json:ground_truth.
Ids: 1, 5, 12, 21, 41. Không đổi nguồn sau khi xem kết quả judge.

Pass 1 đưa (A, B) vào đúng vị trí; pass 2 đưa (B, A), winner của pass 2 đã được quy đổi về
nhãn A/B gốc trước khi so sánh. Final = winner chung nếu hai lượt đồng ý, ngược lại là tie.

| id | Candidate A (pipeline) | Candidate B (fixture) | winner_pass1 | winner_pass2 (A/B gốc) | final_winner | position_consistent | Scores pass 1 | Scores pass 2 |
|---|---|---|---|---|---|---|---|---|
| 1 | 3 ngày làm việc khi kết hôn | 3 ngày làm việc có lương | B | B | B | true | A 0.8 / B 1.0 | A 0.8 / B 1.0 |
| 5 | "Không tìm thấy." | Giám đốc phòng ban phê duyệt | B | A | tie | false | A 0.0 / B 0.5 | A 0.5 / B 0.0 |
| 12 | 1 tháng lương, nhắc lại điều kiện ≥6 tháng | 1 tháng lương | A | tie | tie | false | A 1.0 / B 0.8 | A 1.0 / B 1.0 |
| 21 | 18 ngày phép; nói không có thông tin lương | 18 ngày phép; lương 20–35 triệu | B | B | B | true | A 0.8 / B 1.0 | A 0.8 / B 1.0 |
| 41 | 15 ngày phép năm có lương (v2024) | 12 ngày phép năm (v2023 cũ) | A | A | A | true | A 1.0 / B 0.0 | A 1.0 / B 0.0 |

Reasoning tóm tắt từng lượt (đã quy về A/B gốc):

- **q1** — cả hai lượt: B nêu thêm "có lương", là ý quan trọng của chính sách; A đúng nhưng thiếu ý này.
- **q5** — pass 1: B sai người phê duyệt nhưng "gần đúng hơn" câu từ chối. Pass 2: câu sai người phê duyệt
  bị phạt vì cần Tổng Giám đốc, câu từ chối "không đưa thông tin sai". Judge đổi ý theo vị trí.
- **q12** — pass 1: A nêu rõ điều kiện ≥6 tháng nên tốt hơn. Pass 2: cả hai đều đúng và đủ → tie.
- **q21** — cả hai lượt: B có khoảng lương Senior, A thiếu thông tin lương.
- **q41** — cả hai lượt: A theo chính sách v2024 hiện hành, B dùng v2023 đã bị thay.

Lưu ý khi đọc log: `reasoning_pass2` gọi tên answer theo **vị trí trong lượt 2** (Answer A của lượt 2 là
B gốc). Ví dụ q41 pass 2 viết "Answer B chính xác theo v2024" — đó là A gốc; winner trong artifact đã quy
đổi đúng.

Position bias count/rate: 2/5 = 0.40 (q5, q12).
Verbosity win rate: 0.667; decisive cases: 3 (a_wins_a_longer = 1, b_wins_b_longer = 1).

**Hai case không nhất quán.** q5 là cặp mà *cả hai* answer đều không đạt (A từ chối, B sai người
phê duyệt). Pass 1 chọn B, đang ở vị trí thứ hai; pass 2 chọn A gốc, lúc này cũng ở vị trí thứ hai.
Judge chọn **vị trí thứ hai** trong cả hai lượt và dựng lý do khác nhau cho mỗi lượt — dấu hiệu
position bias thật khi không có lựa chọn đúng. q12 là cặp hai answer cùng đúng; độ chênh 1.0 vs 0.8 ở pass 1 biến mất ở
pass 2, cho thấy chênh lệch nhỏ về văn phong là không ổn định. Swap-and-average biến cả hai thành tie,
đúng với thực tế "không bên nào tốt hơn rõ ràng".

**Winner dài hơn.** Trong 3 case decisive, winner dài hơn ở q1 (B dài hơn, thắng) và q41 (A dài hơn,
thắng); q21 thì B ngắn hơn A nhưng vẫn thắng. Đọc nội dung: ở q1, phần dài hơn là ý "có lương" có trong
reference; ở q41, A dài hơn vì nêu "có lương" nhưng lý do thắng là con số 15 đúng phiên bản v2024 so với 12
của v2023. Ở cả hai, answer dài hơn **cũng là answer đúng hơn**. Vì vậy 0.667 là dấu hiệu thống kê
trùng với độ chính xác, không chứng minh judge thưởng cho độ dài. q21 là phản ví dụ: answer dài hơn
(A, có câu rào đón về lương) thua answer ngắn hơn có đủ thông tin.

## Calibration đúng model_answer

Helper đánh giá đúng question/model_answer đang có trong fixtures/human_labels_10q.json;
không lấy answer mới của pipeline. Prompt chỉ nhận question, answer, reference.
Không gửi human_label, human_note hoặc phân bố nhãn human vào prompt.

| question_id | model_answer gốc | Judge label | Judge reasoning (tóm tắt) | human_label | agree |
|---|---|---|---|---|---|
| 1 | Nhân viên được nghỉ 3 ngày làm việc có lương khi kết hôn. | 1 | Chính xác, đầy đủ theo reference | 1 | yes |
| 5 | Cần Giám đốc phòng ban phê duyệt. | 0 | Trên 50 triệu cần Tổng Giám đốc, không phải Giám đốc phòng ban | 0 | yes |
| 12 | Nhân viên được thưởng Tết tối thiểu 1 tháng lương. | 1 | Đúng mức 1 tháng lương; reasoning nói answer "nêu rõ điều kiện" dù answer không nêu | 1 | yes |
| 21 | Được nghỉ 18 ngày phép (15 cơ bản + 3 thâm niên). Lương Senior từ 20 đến 35 triệu. | 1 | Đúng số ngày phép và khoảng lương Senior | 1 | yes |
| 23 | Hoàn trả 25 triệu vì chưa đủ 1 năm cam kết. | 1 | Đúng số tiền và lý do chưa đủ 1 năm | 1 | yes |
| 29 | Trưởng phòng phê duyệt. Phạt 2% tháng trên 8 triệu. | 0 | Thiếu Kế toán trưởng; phí phạt tính sai | 0 | yes |
| 33 | Phép: 19 ngày. Phụ cấp: 1.500.000 VNĐ/tháng. | 1 | Đúng số ngày phép và tổng phụ cấp | 1 | yes |
| 41 | Nhân viên được nghỉ 12 ngày phép năm. | 0 | Dùng v2023 cũ thay vì v2024 (15 ngày) | 0 | yes |
| 46 | Nhân viên thử việc không được nghỉ phép năm và phải xin nghỉ không lương nếu cần. | 1 | Đúng theo reference | 1 | yes |
| 50 | Được, miễn là đảm bảo kết nối an toàn. | 0 | Chính sách cấm VPN cá nhân | 0 | yes |

Cohen’s κ: 1.0.
Observed/chance agreement và diễn giải: p_o = 10/10 = 1.00. Judge và human đều có 6 nhãn 1 và 4 nhãn 0,
nên p_e = 0.6 × 0.6 + 0.4 × 0.4 = 0.52. κ = (p_o − p_e) / (1 − p_e) = (1.00 − 0.52) / 0.48 = 1.0 —
đồng thuận hoàn toàn, vượt ngưỡng 0.6. Kết quả này đạt được trên bộ nhãn mà sai sót đều là lỗi nội dung rõ
ràng (sai người phê duyệt, sai phiên bản, sai phủ định), nên chưa chứng minh judge ổn định trên các
trường hợp mơ hồ.

## Giới hạn và cách dùng judge

- **Mẫu nhỏ:** 5 cặp pairwise và 10 nhãn nhị phân. Position bias 0.40 có khoảng tin cậy rất rộng (1 cặp
  thay đổi là chênh 0.20); κ = 1.0 trên 10 nhãn không loại trừ khả năng lệch trên bộ lớn hơn.
- **Cùng họ model:** judge `gpt-4o-mini` cũng là model sinh answer A, nên có thể ưu ái cách diễn đạt của
  chính nó. Chưa thử judge khác họ (ví dụ Claude) để so sánh.
- **Prompt:** đã nói rõ "độ dài và vị trí không phải tiêu chí" và xếp độ chính xác so với reference lên
  đầu, nhưng q5 vẫn đổi winner theo vị trí. Prompt chưa có hướng dẫn cho trường hợp cả hai đều sai; đề xuất
  thêm quy tắc "nếu cả hai sai thông tin cốt lõi → tie" và đo lại position bias.
- **Reasoning không luôn trung thực với answer:** q12 nhãn đúng nhưng reasoning nói answer "nêu rõ điều
  kiện ≥6 tháng", trong khi model_answer không nhắc điều kiện này. Nhãn đúng không đảm bảo lý do đúng,
  nên reasoning chỉ dùng để gợi ý, không làm bằng chứng.
- **Không có case lệch nhãn với human trong run này,** nên chưa phân tích được kiểu lỗi nhãn của judge. Cách kiểm chứng
  tiếp: thêm 20–30 nhãn human vào các câu mơ hồ (đáp án đúng một phần như q21/q30 của Phase A), chạy lại
  `python scripts/run_experiments.py --phase b --live` và theo dõi κ cùng position bias.
- **Cách dùng:** judge chỉ dùng như tín hiệu xếp hạng có swap bắt buộc; mọi cặp không nhất quán coi là tie;
  không dùng judge một lượt hoặc judge không có reference làm đáp án tuyệt đối, và lấy mẫu kiểm tra human
  định kỳ trước khi dùng điểm judge làm CI gate.
