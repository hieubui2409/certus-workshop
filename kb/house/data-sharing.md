# Nội quy nhà — chính sách chia sẻ dữ liệu

Áp dụng cho mọi thứ rời khỏi máy của đội: prompt gửi cho mô hình, log, bản
ghi trace, cassette, evidence ledger, ảnh chụp màn hình dán vào ticket.

## 1. Nguyên tắc gốc: danh sách chặn chỉ được THÊM

Danh sách chặn là **hằng số trong mã nguồn**. Cấu hình chỉ được **thêm** mẫu
vào danh sách, **không bao giờ được bớt**.

```
DANH SÁCH CHẶN CUỐI CÙNG = HẰNG SỐ TRONG MÃ  +  phần thêm từ cấu hình
```

Một cấu hình có khả năng **thay** cả danh sách là một cấu hình có khả năng làm
rỗng nó. Ai muốn né một chiều chỉ cần xoá hàng đó khỏi tờ, và mọi phép kiểm
sẽ báo xanh. Đây là dạng lỗi nguy hiểm nhất trong nhóm này vì nó **trông
giống một tính năng**.

## 2. Danh sách chặn tối thiểu

Theo tên file: `*.env` · `*.pem` · `*.key` · `*_secret*` · `credentials*` ·
`id_rsa*` · `*.p12` · `*.keystore`

Theo nội dung (bắt buộc có, ngoài chặn theo tên): chuỗi khớp `sk_live_` ·
`sk_test_` · `whsec_` · `AKIA[0-9A-Z]{16}` · `BEGIN [A-Z ]*PRIVATE KEY` ·
`password\s*=` · `Authorization:\s*Bearer`.

Chặn theo tên file **một mình là không đủ**: bí mật hay bị dán vào README, vào
ticket, vào comment, vào output của test.

## 3. Ngoại lệ giải bằng allowlist hẹp, không bằng cách nới danh sách chặn

Nhu cầu chính đáng: đội cần phân tích `.env.example` để biết ứng dụng cần
những biến nào. Cách sai là bỏ mẫu `*.env` khỏi danh sách chặn — làm thế thì
`.env` thật cũng lọt. Cách đúng:

```yaml
allowlist:
  - path: ".env.example"
    reason: "file mẫu, không chứa giá trị thật; cần để dựng danh sách biến"
```

Ba ràng buộc của một mục allowlist: khớp **đúng một tên file** (không dùng ký
tự đại diện) · **bắt buộc** có `reason` · nội dung vẫn phải đi qua bộ lọc theo
nội dung ở mục 2.

## 4. Ba mức dữ liệu

| Mức | Ví dụ | Được rời khỏi máy không |
|---|---|---|
| công khai | mã nguồn mã nguồn mở, tài liệu chuẩn | có |
| nội bộ | mã nguồn dự án, tên biến, cấu trúc thư mục | có, nếu người dùng đã đồng ý |
| bí mật | khoá, token, mật khẩu, dữ liệu khách hàng thật | **không, trong mọi trường hợp** |

Không có mức nào cho phép *"bí mật nhưng chỉ trong log thôi"*. Log là nơi bí
mật sống lâu nhất.

## 5. Bốn nơi phải kiểm sau mỗi lần chạy

Một chuỗi bí mật bị lọt thường xuất hiện ở nhiều nơi cùng lúc. Kiểm đủ bốn:

1. prompt gửi cho mô hình
2. log ứng dụng
3. bản ghi trace / cassette
4. evidence ledger

Phép kiểm nhanh: `grep -r "sk_live\|BEGIN PRIVATE KEY\|password=" <thư mục>` →
phải ra **0 dòng**.

## 6. Bảng dữ liệu phải hiện ra, không được ngầm

Mọi file bị loại khỏi phân tích phải được **liệt kê kèm lý do**, ở nơi người
dùng thấy mặc định — không giấu trong tab phụ đóng sẵn. Loại bỏ im lặng là
một dạng giấu mẫu số: người đọc không biết con số họ đang nhìn được tính trên
bao nhiêu file.
