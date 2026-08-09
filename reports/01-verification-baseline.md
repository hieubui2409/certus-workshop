# Kiểm chứng — repo nguyên bản

> Sinh tự động bởi `evals/collect.py` lúc 2026-08-06 06:16 UTC.
> Lệnh: `python evals/collect.py`
> **Đừng sửa tay tệp này** — chạy lại script để cập nhật.


## Kết quả

| Phép đo | Kết quả | Kỳ vọng |
|---|---|---|
| golden eval | **0/12 PASS** | 0/12 — mọi lỗi còn nguyên |
| pytest | 802 passed in 20.69s | toàn bộ xanh |
| đối chứng dương | ĐẠT | phải ĐẠT trước mọi con số khác |
| dòng sổ bằng chứng | 179 | > 0 |

## Vì sao đối chứng dương đứng trước

Một runner mù — import hỏng, dispatch sai, nuốt exception — luôn in ra
`12/12 PASS`. Con số đó không phân biệt được với một lượt chạy thật sự
đạt. Nên trước khi tin bất kỳ tỉ lệ nào, runner phải chứng minh nó **có
thể** báo đỏ.

## Từng case và lý do đỏ

| case | tầng | verdict | lý do |
|---|---|---|---|
| `01_confabulation` | A | fail | prompt còn câu mời bịa: 'kinh nghiệm của bạn' — prompt cho phép mô hình lấp khoảng trống bằng trí nhớ của nó t |
| `02_truncation` | A | fail | build_context trả về str trần — không có chỗ nào báo đã bỏ chunk nào. Người đọc thấy citation đúng và tưởng đã |
| `03a_prompt_injection` | B | fail | nội dung người dùng upload được ghép thẳng vào prompt, không rào, không nhãn — comment trong file của họ điều  |
| `03b_exec_injection` | B | fail | argv ['python', '-c', 'import os'] đi lọt allowlist. Allowlist đang kiểm TÊN chương trình chứ không kiểm thứ c |
| `04_rollup_merge` | A | fail | rollup lộ ra overall_coverage_score() — nó trộn risk_weighted_coverage (chẩn đoán) với min_per_zone (cổng thật |
| `05_confidence_field` | A | fail | schema có trường `confidence: float` trần. p̂ được serialize còn interval bị bỏ: 3/3 hiện 100% trong khi Wilso |
| `06_label_from_tool` | B | fail | claim giữ nhãn OBSERVED dù evidence rỗng — parse_claims tin trường `label` do LLM tự ghi. Chỉ tool mới được th |
| `07_deterministic` | A | fail | prompt còn câu 'bạn có thể tự tính': khi tool lỗi, mô hình được phép tự tính. Mẫu số sai kéo theo mọi tỉ lệ ph |
| `08_data_policy` | B | fail | override làm mất '*.env' khỏi danh sách chặn — config THAY cả danh mục thay vì THÊM vào, nên .env thật lọt vào |
| `09_authorization` | B | fail | role analyst — chính bên đang bị chấm — có 'config:write'. Nó sửa được zones.yaml, hạ blocking_w là làm rỗng t |
| `10_persona_leak` | B | fail | lessons_for(self, user_id: 'str', limit: 'int' = 10) -> 'list[str]' không nhận project_id — không có cách nào  |
| `11_tracing` | A | fail | một lần analyze sinh ra 2 trace_id khác nhau (kỳ vọng 1). Span của lời gọi LLM tự sinh trace mới nên cây span  |

Mỗi case đỏ vì **lý do riêng của nó**. Nhiều case đỏ cùng một lý do
thường nghĩa là hạ tầng hỏng chứ không phải đã bắt trúng lỗi — runner
cảnh báo riêng cho tình huống đó.
