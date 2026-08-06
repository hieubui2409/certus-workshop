# WCAG 2.2 — Hướng dẫn về khả năng tiếp cận nội dung web

Tài liệu tham chiếu nội bộ. Diễn giải lại W3C Recommendation 05/10/2023 bằng
tiếng Việt, phục vụ đội phát triển và đội QA.

## 1. Phạm vi

WCAG 2.2 áp dụng cho nội dung web: văn bản, hình ảnh, âm thanh, mã đánh dấu
và mã kịch bản tạo ra giao diện. Tài liệu này không quy định công nghệ cụ
thể, không quy định quy trình phát triển, và không thay thế thử nghiệm với
người dùng thật.

## 2. Bốn nguyên tắc

| Nguyên tắc | Nội dung phải |
|---|---|
| Cảm nhận được | trình bày được theo cách người dùng nhận biết được |
| Vận hành được | thao tác được bằng bàn phím và các thiết bị hỗ trợ |
| Hiểu được | dễ đọc, dễ đoán, có hỗ trợ khi nhập liệu sai |
| Bền vững | phân tích được bởi công nghệ hỗ trợ hiện tại và tương lai |

## 3. Ba mức tuân thủ

Mỗi tiêu chí thành công thuộc đúng một mức: A, AA hoặc AAA. Mức AA bao gồm
toàn bộ tiêu chí mức A; mức AAA bao gồm cả A và AA.
W3C khuyến nghị không lấy mức AAA làm chính sách bắt buộc cho cả trang web.

## 4. Tiêu chí không có nội dung áp dụng vào

Đây là điều khoản bị hiểu nhầm nhiều nhất. Nếu không có nội dung nào mà một tiêu chí thành công áp dụng vào, thì tiêu chí thành công đó được coi là đã thoả mãn.

Nói cách khác: một trang không có video thì tiêu chí về phụ đề **đã đạt**, chứ
không phải **chưa đạt**, và cũng không cần khai báo gì thêm. Im lặng không bị
tính là trừ điểm. Đây là điểm khác biệt căn bản với OWASP ASVS — xem
`kb/standards/owasp-asvs.md` mục 3 — và là chỗ hai chuẩn mâu thuẫn nhau một
cách có thật.

## 5. Năm điều kiện tuân thủ

1. **Mức tuân thủ** — đáp ứng toàn bộ tiêu chí của mức đã công bố, hoặc cung
   cấp một phiên bản thay thế tuân thủ.
2. **Trang đầy đủ** — tuân thủ tính cho cả trang, không tính cho một phần.
3. **Quy trình đầy đủ** — mọi trang trong một quy trình (ví dụ: giỏ hàng →
   thanh toán → xác nhận) đều phải tuân thủ, nếu không cả quy trình không
   tuân thủ.
4. **Chỉ dùng cách thức bền vững** — thông tin phải truyền tải được bằng
   công nghệ mà công nghệ hỗ trợ đọc được.
5. **Không cản trở** — công nghệ không được dùng theo cách phá vỡ khả năng
   tiếp cận của phần còn lại.

## 6. Điều tài liệu này KHÔNG nói

- Không quy định ngưỡng phần trăm nào cho việc kiểm thử.
- Không quy định số lượng người dùng tối thiểu khi thử nghiệm.
- Không quy định công cụ kiểm tra tự động nào là bắt buộc.

Kiểm tra tự động chỉ phát hiện được một phần các vi phạm. W3C nêu rõ rằng
đánh giá tuân thủ cần có bước rà thủ công.

## 7. Chín tiêu chí mới của 2.2 so với 2.1

`2.4.11` và `2.4.12` Focus Not Obscured (Minimum/Enhanced) · `2.4.13` Focus
Appearance · `2.5.7` Dragging Movements · `2.5.8` Target Size (Minimum) ·
`3.2.6` Consistent Help · `3.3.7` Redundant Entry · `3.3.8` và `3.3.9`
Accessible Authentication (Minimum/Enhanced).

Tiêu chí `4.1.1` Parsing đã bị **gỡ bỏ** khỏi WCAG 2.2.
