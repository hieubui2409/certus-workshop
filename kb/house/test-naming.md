# Nội quy nhà — quy ước đặt tên ca kiểm thử

Áp dụng cho mọi repo Python của đội. Mục đích không phải cho đẹp: tên ca kiểm
là thứ duy nhất người trực đêm đọc được khi CI đỏ lúc 2 giờ sáng.

## 1. Khuôn tên

```
test_<đối tượng>_<điều kiện>_<kết quả mong đợi>
```

Tên phải trả lời được câu *"cái gì hỏng?"* mà không cần mở file.

| Không đạt | Đạt |
|---|---|
| `test_charge` | `test_thu_tien_vuot_tran_thi_bi_tu_choi` |
| `test_case_2` | `test_idempotency_key_tra_ve_dung_giao_dich_cu` |
| `test_it_works` | `test_gio_rong_bi_tu_choi` |

Tên viết bằng tiếng Việt không dấu; định danh trong mã nguồn (hàm, lớp, biến)
viết bằng tiếng Anh. Đây là quy ước có chủ đích: tên ca kiểm là câu nói với
con người, tên hàm là câu nói với trình biên dịch.

## 2. Bố cục file

| Vị trí | Quy ước |
|---|---|
| thư mục | `tests/` ngang hàng với gói mã nguồn |
| tên file | `test_<tên module>.py`, một file cho một module |
| fixture dùng chung | `tests/conftest.py` |
| dữ liệu mẫu | hàm dựng trong chính file kiểm, không dùng file JSON rời |

## 3. Một ca kiểm, một lý do đỏ

Một ca kiểm chỉ được đỏ vì **một** lý do. Nếu phải viết `and` trong câu mô tả
lý do, hãy tách thành hai ca.

Ngoại lệ được chấp nhận: các assert cùng mô tả **một** kết quả (ví dụ kiểm cả
`status` lẫn `refundable` của cùng một lần hoàn tiền).

## 4. Assert phải có nội dung

Cấm ba dạng assert rỗng nghĩa:

```python
assert result is not None        # không nói gì
assert len(items) >= 0           # luôn đúng
assert True                      # ...
```

Một ca kiểm mà mọi assert đều đúng-hiển-nhiên vẫn chạm đủ mọi dòng và vẫn làm
độ phủ dòng đẹp lên. Đó là lý do độ phủ dòng không bao giờ là mẫu số cuối
cùng.

## 5. Ca kiểm cho đường chạy song song

Nếu một hàm được nhiều luồng gọi, ca kiểm phải:

1. chạy **nhiều luồng cùng lúc trên cùng một đối tượng bị tranh chấp**, và
2. assert vào **trạng thái cuối** (số dư, tổng, độ dài hàng đợi), không chỉ
   assert vào số lần gọi hay số dòng nhật ký.

Assert vào số dòng nhật ký là bẫy: thao tác thêm vào danh sách vốn đã an toàn
với luồng, nên ca kiểm sẽ xanh trong khi dữ liệu thật đã sai. Xem
`fixtures/targets/ledger/README.md` cho một ca có thật.

## 6. Đặt tên cho ca kiểm sinh tự động

Ca kiểm do công cụ sinh phải mang tiền tố `test_gen_` và ghi rõ trong docstring
**ô lưới nào** nó phục vụ:

```python
def test_gen_cell_customer_tier_vip_shipping_zone_international():
    """cell:customer_tier=vip|shipping_zone=international"""
```

Chuỗi trong docstring phải khớp **đúng từng ký tự** với `cell_id` chuẩn tắc.
Đây là sợi dây duy nhất nối một ca kiểm với ô lưới mà nó chấm.
