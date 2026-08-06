# shopcart — logic giỏ hàng

Repo mẫu **lành mạnh** dùng làm dữ liệu đầu vào cho CERTUS. Không có lỗi cài
cắm ở đây. Mọi lỗi của workshop nằm trong CERTUS, không nằm trong repo này.

```bash
python -m pytest -q
python -m coverage run --source=shopcart -m pytest -q && python -m coverage report -m
```

## Nghiệp vụ

`checkout(items, tier, zone, method, coupon)` trả về một `Quote`. Thứ tự tính
là load-bearing:

1. tiền hàng (`pricing.subtotal`)
2. trừ giảm giá theo hạng khách + theo mã, áp trần 50% (`pricing.cap_discount`)
3. phí ship tính trên tiền hàng **sau giảm** (`shipping.shipping_fee`)
4. phụ phí thanh toán tính trên (hàng sau giảm + ship), có trần (`payment.payment_fee`)

## Bốn trục biến thiên tự nhiên

Mỗi trục phân giải được về một enum có thật trong mã nguồn — đây là `ref` mà
`admit_axis()` của CERTUS đòi hỏi:

| Trục | `ref` | Số giá trị |
|---|---|---|
| `customer_tier` | `shopcart/enums.py::CustomerTier` | 3 |
| `shipping_zone` | `shopcart/enums.py::ShippingZone` | 3 |
| `payment_method` | `shopcart/enums.py::PaymentMethod` | 3 |
| `coupon_type` | `shopcart/enums.py::CouponType` | 4 |

Không gian tổ hợp: **108** tổ hợp đầy đủ, **63** ô ở mức t=2 (pairwise).

## Vì sao repo này đáng để đo

Bộ kiểm thử ở đây giống hệt một dự án thật đang chạy tốt:

- `python -m pytest -q` → **41 passed**
- line coverage → **98%** (chỉ hụt 4 dòng ở `report.py`)
- nhưng ở tầng `checkout()`, test chỉ chạm **7 tổ hợp đầy đủ**, phủ **28/63**
  ô pairwise (**44%**).

Cụ thể, chưa ca kiểm nào chạy `checkout()` với `PaymentMethod.WALLET`, và
chưa ca nào ghép `ShippingZone.INTERNATIONAL` với `CustomerTier.VIP`. Các
nhánh code liên quan **đã chạy** ở unit test nên line coverage không hề hay
biết — đó chính là bài học "line coverage cao mà grid thưa".

Không có gì sai trong repo này. Chỉ có một mẫu số bị giấu đi.
