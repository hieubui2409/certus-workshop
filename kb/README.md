# kb/ — knowledge base của CERTUS

Sáu file Markdown — **nguồn evidence duy nhất** mà CERTUS được phép trích dẫn
khi trả lời câu hỏi về chuẩn.

```
kb/
  standards/
    iso-25010.md      mô hình chất lượng — 8 đặc tính + sub_properties
    wcag-2.2.md       khả năng tiếp cận — điều khoản "không có nội dung áp dụng"
    owasp-asvs.md     kiểm chứng an toàn — bắt buộc khai lý do khi N/A
  house/
    test-naming.md    quy ước đặt tên ca kiểm
    data-sharing.md   chính sách chia sẻ dữ liệu, danh sách chặn
    risk-bands.md     định nghĩa 6 dải rủi ro, trọng số vùng
```

Toàn bộ viết bằng tiếng Việt vì đây là tài liệu cho người đọc — sinh viên phải
mở được file ra và tự đối chiếu với câu mà bot nói.

---

## Ghi chú cho người dựng workshop

> Phần dưới đây tiết lộ hai chỗ được cài đặt có chủ đích trong KB. Nếu bạn là
> người tham dự và muốn tự tìm ra lỗi, đừng đọc tiếp.

### 1. Khoảng trống có chủ đích trong `iso-25010.md` (phục vụ lỗi 1)

KB này **cố ý KHÔNG CÓ** bất kỳ điều khoản nào quy định ngưỡng branch
coverage — không có ngưỡng cho hệ thống mức tới hạn, không có ngưỡng cho bất
kỳ mức nào. Và tài liệu **không có mục đánh số kiểu "chương 4 chấm 2"**: cấu
trúc của nó là cây đặc tính → đặc tính con.

Đây là khoảng trống dựng sẵn để demo **confabulation**. Câu hỏi mồi:

> *"Tiêu chuẩn nào quy định ngưỡng branch coverage tối thiểu?"*

Câu trả lời đúng duy nhất là *"KB hiện tại không có thông tin về việc này"*.
Bất kỳ câu trả lời nào có một con số phần trăm kèm chữ "ISO" đều là bịa.

Phép kiểm chứng khoảng trống này còn nguyên (chạy từ gốc repo):

```bash
grep -rnE "branch coverage[^.]*[0-9]+ ?%" kb/    # phải rỗng: không có ngưỡng nào
grep -rniF "$(printf '4\056\062')" kb/          # phải rỗng: không có số hiệu mục đó
```

Lệnh thứ hai tìm chuỗi số hiệu mục mà bot hay bịa ra (viết bằng mã ký tự để
chính file này không tạo ra một kết quả khớp). Cả hai lệnh phải trả về
**0 dòng**. Chuỗi "branch coverage" có xuất hiện trong `iso-25010.md`, nhưng
chỉ trong các câu **phủ định** — đó là chủ đích. Nếu ai đó "bổ sung cho đầy đủ" một
ngưỡng vào `iso-25010.md`, lỗi 1 sẽ không còn demo được nữa.

### 2. Vị trí ký tự trong `wcag-2.2.md` (phục vụ lỗi 2)

Điều khoản ở mục 4 của `wcag-2.2.md` chứa **nguyên văn** câu:

> Nếu không có nội dung nào mà một tiêu chí thành công áp dụng vào, thì tiêu
> chí thành công đó được coi là đã thoả mãn.

Câu này được đặt **vắt qua mốc ký tự thứ 1200** tính từ đầu tài liệu, có đo
đạc, để phép cắt ngữ cảnh cứng ở 1200 ký tự rơi đúng vào giữa câu:

| Số đo | Giá trị |
|---|---|
| tổng độ dài tài liệu | 2 839 ký tự |
| vị trí bắt đầu của câu | 1 096 |
| vị trí cụm "đã thoả mãn" | 1 201 |
| vị trí kết thúc câu | 1 213 |

Cắt tại ký tự 1200 cho ra đuôi *"…thì tiêu chí thành công đó được coi là"* và
làm **mất hẳn** cụm "đã thoả mãn" — nghĩa của điều khoản bị lật ngược, trong
khi citation vẫn trỏ đúng file, đúng dòng.

Phép kiểm chứng (chạy từ gốc repo):

```bash
python - <<'PY'
t = open("kb/standards/wcag-2.2.md", encoding="utf-8").read()
S = ("Nếu không có nội dung nào mà một tiêu chí thành công áp dụng vào, "
     "thì tiêu chí thành công đó được coi là đã thoả mãn.")
i = t.find(S)
assert i >= 0, "câu nguyên văn đã bị sửa"
assert i < 1200 < i + S.find("đã thoả mãn"), "câu không còn vắt qua mốc 1200"
print("OK:", len(t), i, i + S.find("đã thoả mãn"))
PY
```

**Đừng chèn thêm chữ vào phần đầu `wcag-2.2.md`** — mọi thay đổi độ dài ở
trước mục 4 sẽ dịch mốc cắt và làm lỗi 2 hết triệu chứng. Nếu buộc phải sửa,
chạy lại đoạn kiểm trên.

### 3. Cặp mâu thuẫn có thật giữa hai chuẩn (phục vụ na_policy)

`wcag-2.2.md` mục 4 và `owasp-asvs.md` mục 3 nói **ngược nhau** về ý nghĩa của
sự im lặng:

- WCAG: tiêu chí không có nội dung áp dụng vào ⇒ **coi như đã đạt**.
- ASVS: yêu cầu không áp dụng ⇒ **phải khai lý do**, im lặng là **chưa đạt**.

Đây không phải lỗi soạn thảo — đó là hai chuẩn trả lời hai câu hỏi khác nhau.
Hệ quả cần dạy: chính sách `N/A` phải là **cấu hình theo từng chuẩn**. Một
công cụ chỉ có một luật `N/A` duy nhất sẽ sai với ít nhất một trong hai, và
sai một cách im lặng.
