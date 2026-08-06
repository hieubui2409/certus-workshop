# OWASP ASVS — Chuẩn kiểm chứng an toàn ứng dụng

Tài liệu tham chiếu nội bộ. Diễn giải lại Application Security Verification
Standard bằng tiếng Việt.

## 1. ASVS là gì

Một danh sách **yêu cầu kiểm chứng** (verification requirement) cho ứng dụng
web và API. Khác với một bảng phân loại từ vựng, ASVS được viết để **đem ra
kiểm** — mỗi yêu cầu là một câu có thể trả lời *đạt* hoặc *không đạt*, kèm
bằng chứng.

## 2. Ba mức

| Mức | Dành cho | Ý nghĩa |
|---|---|---|
| L1 | mọi ứng dụng | mức sàn, kiểm được từ bên ngoài |
| L2 | ứng dụng xử lý dữ liệu nhạy cảm | mức khuyến nghị cho phần lớn hệ thống |
| L3 | ứng dụng tới hạn cao | y tế, tài chính, hạ tầng trọng yếu |

Mức cao bao trùm toàn bộ yêu cầu của mức thấp hơn.

## 3. Yêu cầu không áp dụng thì phải KHAI LÝ DO

Đây là điều khoản quan trọng nhất của tài liệu này với đội mình, và là chỗ
ASVS **ngược hẳn** với WCAG:

> Một báo cáo kiểm chứng theo ASVS phải nêu rõ **phạm vi**, và với mỗi yêu cầu
> bị đánh dấu **không áp dụng**, báo cáo phải **ghi lý do** vì sao nó không áp
> dụng cho hệ thống này. Một yêu cầu bị bỏ trống, không đánh dấu, không kèm lý
> do thì **không được tính là đạt**.

Nói cách khác, trong ASVS: **im lặng là chưa đạt.**

### 3.1. Cặp mâu thuẫn có thật giữa hai chuẩn

| | WCAG 2.2 | OWASP ASVS |
|---|---|---|
| Tiêu chí không có nội dung áp dụng vào | **được coi là đã thoả mãn** | **phải khai lý do**, nếu không thì chưa đạt |
| Im lặng nghĩa là gì | đã đạt | chưa đạt |
| Cần ghi chú không | không | có, bắt buộc |

Xem `kb/standards/wcag-2.2.md` mục 4 cho vế còn lại.

Đây **không phải** lỗi của chuẩn nào cả. Hai chuẩn trả lời hai câu hỏi khác
nhau: WCAG hỏi *"nội dung này có rào cản tiếp cận không"*, ASVS hỏi *"đội này
đã kiểm chứng những gì"*. Một hệ thống áp cùng lúc cả hai chuẩn **không thể**
dùng chung một chính sách `N/A`, và đây chính là lý do chính sách `N/A` phải
là **cấu hình theo từng chuẩn**, không phải một hằng số toàn cục.

Hệ quả cho công cụ tự động: một công cụ chỉ có một luật `N/A` duy nhất sẽ sai
với ít nhất một trong hai chuẩn, và nó sẽ sai **một cách im lặng**.

## 4. Bốn nguỵ biện bị từ chối khi khai `N/A`

Lý do khai `N/A` phải nói về **cấu trúc hệ thống**, không nói về xác suất hay
độ khó. Bốn dạng lý do bị từ chối thẳng:

| Nguỵ biện | Vì sao bị từ chối |
|---|---|
| *hiếm khi xảy ra* | hiếm không phải là không thể |
| *khó kiểm quá* | độ khó là vấn đề của đội, không phải thuộc tính của hệ |
| *ít người dùng đụng tới* | ít người vẫn là người |
| *hệ thống sẽ tự chặn* | nếu chắc thế thì hãy kiểm đúng chỗ chặn đó |

Lý do hợp lệ có dạng: *"hệ thống không có thành phần X, nên yêu cầu về X
không có đối tượng để áp dụng"* — và nêu được cách kiểm chứng rằng X thật sự
không tồn tại.

## 5. Điều tài liệu này KHÔNG nói

- Không quy định ngưỡng độ phủ mã nguồn nào.
- Không quy định công cụ cụ thể nào phải dùng.
- Không nói tự khai là đủ: mỗi yêu cầu cần bằng chứng kiểm chứng được, và
  bên tự khai không phải là bên phê duyệt.
