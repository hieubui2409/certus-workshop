# ToT × Grid-Coverage harness — mã nguồn tham khảo

`TestCoverageEvaluation.zip` (4.8 MB) là **bộ đo** hiện thực hoá phần lý thuyết
trong [`../02-tot-grid-coverage.md`](../02-tot-grid-coverage.md). Đây là mã
nguồn để đọc và nghiên cứu, không phải một phần của CERTUS.

```bash
unzip TestCoverageEvaluation.zip
```

Giải nén ra thư mục `harness/`:

| thư mục | nội dung |
|---|---|
| `README.md` | tài liệu chính — đọc file này trước |
| `data/config-keys.d/` | khai báo từng nhóm cấu hình: trục, vùng rủi ro, ngưỡng, ngân sách |
| `scripts/` | phần lõi chạy phép đo |
| `agents/` | vai trò cho mô hình: đề xuất trục, viết probe |
| `hooks/`, `adapters/`, `install/` | chặn ghi sai, nối nguồn dữ liệu, cài vào project |
| `skills/grid-probe` | hợp đồng cho mô hình: viết probe cho một ô, đề xuất trục mới, đề xuất ô bất khả thi — nhưng không được phán band/verdict/score |
| `tests/` | bộ test của chính bộ đo |

## Vì sao đáng đọc

Nó trả lời đúng một câu hỏi: *bộ test đã thực sự chạy qua những tổ hợp điều
kiện nào, và phần chưa chạy qua thì nguy hiểm tới đâu?* — và chỉ trả lời từ
**artifact có thật trên đĩa** (kết quả chạy test, báo cáo coverage, kết quả
mutation).

Hai ràng buộc trong đó đáng chú ý, vì cùng một mạch tư tưởng với các lỗ hổng
`04-coverage-meaning` và `06-evidence-probe-first` đã gặp trên lớp:

- **Mô hình không bao giờ được tự phong band chất lượng.** Nó có thể đề xuất
  một trục hay viết một probe, nhưng việc một ô được xếp band nào là do **mã**
  quyết định, chiếu từ artifact. Hỏi mô hình "chỗ này phủ tốt không?" thì phép
  đo đã hỏng từ trước đó rồi.
- **Không tin điều gì chỉ vì nó được viết ra.** Mỗi claim mang một tầng xuất
  xứ, và chỉ tầng `executed` — một lệnh thật sự đã chạy — mới được tính.

Bộ đo này cố ý **không mang sẵn** trục, vùng rủi ro hay ngưỡng của bất kỳ hệ
thống nào: mọi thứ riêng của dự án nằm ở file cấu hình của chính dự án đó. Một
bộ đo mà đã biết trước điều gì về thứ nó đo thì rốt cuộc chỉ đang đo lại giả
định của chính nó.
