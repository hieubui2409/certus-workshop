# fixtures/targets — ba repo mẫu

> **Ba repo này LÀNH MẠNH.** Chúng là *dữ liệu đầu vào* để CERTUS phân tích:
> có code thật, có test thật, và có chỗ test chưa phủ hết một cách **tự nhiên**
> — đúng như mọi dự án thật. Khi kết quả phân tích nói sai về ba repo này, cái
> sai thuộc về công cụ phân tích, không thuộc về repo.

| Repo | Đặc điểm | Trạng thái test |
|---|---|---|
| [`shopcart/`](shopcart/) | giỏ hàng, phí ship, mã giảm giá | 41 passed · line coverage 98% |
| [`ledger/`](ledger/) | sổ cái số dư, ghi có/ghi nợ | 27 passed |
| [`payments/`](payments/) | cổng thanh toán, có cấu hình `.env` | 24 passed |

## Chạy cả ba

```bash
for repo in shopcart ledger payments; do
  ( cd "fixtures/targets/$repo" && python -m pytest -q )
done
```

Mỗi repo tự chứa: một `pytest.ini` với `pythonpath = .`, không phụ thuộc gói
ngoài nào ngoài `pytest`. Không repo nào gọi mạng.

## Ngoài ba repo này

CERTUS còn nhận **upload tự do** — bề mặt để bạn thử phân tích repo của chính
mình. Kéo một thư mục mã nguồn vào, xem công cụ nói gì về độ phủ và những góc
rủi ro chưa ai nhìn.
