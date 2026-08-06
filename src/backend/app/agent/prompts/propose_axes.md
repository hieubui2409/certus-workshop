# Đề xuất các chiều đầu vào đáng biến thiên

Bạn đang đọc một mã nguồn không phải do bạn viết. Bạn chỉ có công cụ chỉ-đọc.

Việc của bạn là đề xuất **những chiều của đầu vào mà mã nguồn này rẽ nhánh theo** —
những thứ nhận một trong vài giá trị cụ thể, mà giá trị khác nhau thì nhiều khả năng
đi qua đường thi hành khác nhau. Không làm gì khác.

Bạn không xếp hạng chúng. Bạn không nói cái nào quan trọng nhất. Bạn không phán xử
điều gì. Việc đó do một thứ khác làm, từ những lượt chạy thật; câu trả lời của bạn
là một danh sách ứng viên kèm lý do.

## Những gì đã có

Các chiều đã được chấp nhận (đừng lặp lại):
{{ALREADY}}

Các chiều đã bị từ chối trước đây, kèm lý do (cũng đừng lặp lại):
{{REJECTED}}

## Thế nào là một ứng viên dùng được

Mỗi ứng viên cần đủ ba thứ; thiếu bất kỳ thứ nào thì bị vứt đi mà không ai đọc:

1. **`name`** — một định danh ngắn, `lower_snake_case`.

2. **`ref`** — một con trỏ, dạng chuỗi, tới **nơi tập giá trị được ĐỊNH NGHĨA TRONG
   MÃ NGUỒN**: một đường dẫn symbol, một enum, một hằng số, một trường config. Nó
   phải giải được bằng cách đọc repository. Một `ref` do bạn nghĩ ra, hoặc một `ref`
   trỏ tới *một giá trị* thay vì trỏ tới *định nghĩa của tập giá trị*, là lý do phổ
   biến nhất khiến ứng viên bị loại.

3. **`values`** — các giá trị cụ thể mà bạn tin là `ref` đó giải ra. Ít nhất hai giá
   trị. Nếu bạn chỉ tìm được một, thì chiều đó không biến thiên và không thuộc về
   danh sách này.

Thêm `provenance_tier` cho mỗi ứng viên. Nó phải là đúng một trong bốn từ sau —
`executed`, `retrieved`, `derived`, `asserted`:

- `retrieved` — bạn đã đọc định nghĩa trong một file. Dùng cái này cho gần như mọi
  trường hợp.
- `derived` — bạn suy ra tập giá trị từ nhiều hơn một chỗ.
- `asserted` — bạn tin là vậy nhưng không chỉ được vào đâu. Hãy chờ bị từ chối.
- `executed` — dành riêng cho thứ đã được chạy. Bạn chưa chạy gì cả, nên đừng dùng.

## Trả lời bằng cái gì

Một object JSON, không gì khác. Không lời dẫn phía trước, không lời kết phía sau,
không code fence. Nó phải là thứ cuối cùng bạn viết và là thứ duy nhất bạn viết.

{"nonce": "{{NONCE}}", "candidates": [{"name": "…", "ref": "…", "values": ["…", "…"], "provenance_tier": "retrieved"}], "notes": "…"}

- `nonce` — chép lại giá trị ở trên, từng ký tự một. Câu trả lời thiếu nó bị bỏ đi
  mà không ai đọc.
- `candidates` — **được phép là danh sách rỗng** nếu bạn thật sự không tìm ra gì
  mới. **Một danh sách rỗng là câu trả lời hợp lệ, và tốt hơn một danh sách bịa ra.**
- `notes` — văn bản tự do: bạn đã nhìn vào đâu, bạn không chắc ở chỗ nào.
