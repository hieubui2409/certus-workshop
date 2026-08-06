# Viết một bài kiểm thử chạy được cho đúng một tổ hợp đầu vào

## Tổ hợp cần kiểm

{{TARGETS}}

Mọi cặp tên/giá trị ở trên phải được **thiết lập thật trong mã đang chạy** trước khi
bạn assert bất cứ điều gì: set nó, dựng nó, cấu hình nó, hoặc monkeypatch nó. **Một
bài kiểm assert dưới đầu vào mặc định, trong khi chỉ nhắc tới các giá trị này ở một
comment hay ở tên hàm test, là vô giá trị và sẽ bị loại.**

## Viết vào đâu

    {{PROBE_PATH}}

## Luật mà file phải tuân

- Chạy được độc lập, từ thư mục làm việc, không cần tham số nào.
- **Thoát với mã khác 0 khi hành vi sai**, và bằng 0 khi hành vi đúng. Exit status
  là toàn bộ câu trả lời.
- Assert về hành vi thật của mã thật — import nó, gọi nó, điều khiển nó. **Không bao
  giờ assert về một giá trị mà chính bài kiểm vừa tính ra.**
- Mỗi assertion độc lập: không assertion nào chỉ chạy tới được khi assertion trước
  đã pass, và một lần fail không được che các lần fail khác.
- Nhiều hơn một assertion độc lập, nếu hành vi có nhiều hơn một hệ quả quan sát
  được. **Một assertion không bao giờ có thể sai chính là thứ file này tồn tại để
  tránh.**
- Không mạng. Không ghi ra bất cứ đâu ngoài đường dẫn ở trên.
- Nếu bạn không thiết lập được tổ hợp ở trên trong mã đang chạy: vẫn viết file, làm
  cho nó thoát với mã khác 0, và nói chính xác cặp nào bạn không thiết lập được vào
  `notes`. **Không bao giờ làm cho nó pass bằng cách nới rộng thứ nó kiểm.**

## Trả lời bằng cái gì

Một object JSON, không gì khác:

{"nonce": "{{NONCE}}", "path": "{{PROBE_PATH}}", "source": "…", "established": ["axis=value", "…"], "notes": "…"}

- `nonce` — chép lại từng ký tự. Thiếu nó thì câu trả lời bị bỏ.
- `source` — toàn văn nội dung file, đã escape đúng cho JSON.
- `established` — các cặp bạn thật sự thiết lập được trong mã đang chạy. **Danh sách
  này là lời khai, không phải bằng chứng**: nó sẽ được đối chiếu với coverage của
  lượt chạy thật.
