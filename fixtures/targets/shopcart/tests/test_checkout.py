"""Kiểm thử đầu-cuối: `checkout()` với vài cấu hình đơn hàng hay gặp.

Ghi chú của đội: đây là các ca xuất hiện nhiều nhất trong log production —
gần như toàn bộ đơn là nội địa, trả bằng thẻ. Còn nhiều tổ hợp khác
(hạng khách × vùng × phương thức × loại mã) chưa ai viết ca kiểm, nhưng các
nhánh code thì đã chạy qua hết ở tầng unit test.
"""

import pytest

from shopcart.cart import checkout
from shopcart.enums import CouponType, CustomerTier, PaymentMethod, ShippingZone
from shopcart.pricing import CartError, Coupon, LineItem


def standard_items():
    return [
        LineItem(sku="ao-thun", unit_price=150_000, quantity=2, weight_g=300),
        LineItem(sku="mu-luoi-trai", unit_price=100_000, quantity=1, weight_g=200),
    ]


def test_don_co_ban_khach_thuong_noi_dia_the():
    quote = checkout(
        standard_items(),
        CustomerTier.STANDARD,
        ShippingZone.DOMESTIC,
        PaymentMethod.CARD,
    )
    assert quote.subtotal == 400_000
    assert quote.discount == 0
    assert quote.shipping == 20_000
    assert quote.surcharge == 6_300
    assert quote.total == 426_300


def test_don_co_ban_thanh_toan_khi_nhan_hang():
    quote = checkout(
        standard_items(),
        CustomerTier.STANDARD,
        ShippingZone.DOMESTIC,
        PaymentMethod.COD,
    )
    assert quote.shipping == 20_000
    assert quote.surcharge == 8_400
    assert quote.total == 428_400


def test_ma_giam_phan_tram_tru_vao_tien_hang():
    coupon = Coupon(code="SALE10", type=CouponType.PERCENT, value=10)
    quote = checkout(
        standard_items(),
        CustomerTier.STANDARD,
        ShippingZone.DOMESTIC,
        PaymentMethod.CARD,
        coupon,
    )
    assert quote.discount == 40_000
    assert quote.shipping == 20_000
    assert quote.total == 385_700


def test_khach_plus_qua_nguong_thi_duoc_mien_ship():
    quote = checkout(
        standard_items(),
        CustomerTier.PLUS,
        ShippingZone.DOMESTIC,
        PaymentMethod.CARD,
    )
    assert quote.discount == 12_000
    assert quote.shipping == 0
    assert quote.total == 393_820


def test_khach_vip_tuyen_khu_vuc_luon_duoc_mien_ship():
    quote = checkout(
        standard_items(),
        CustomerTier.VIP,
        ShippingZone.REGIONAL,
        PaymentMethod.CARD,
    )
    assert quote.discount == 28_000
    assert quote.shipping == 0
    assert quote.total == 377_580


def test_don_quoc_te_dung_ma_giam_tien_mat():
    coupon = Coupon(
        code="GIAM100K", type=CouponType.FIXED, value=100_000, min_subtotal=300_000
    )
    quote = checkout(
        standard_items(),
        CustomerTier.STANDARD,
        ShippingZone.INTERNATIONAL,
        PaymentMethod.CARD,
        coupon,
    )
    assert quote.discount == 100_000
    assert quote.shipping == 120_000
    assert quote.total == 426_300


def test_ma_free_ship_cuu_don_nho():
    coupon = Coupon(
        code="FREESHIP", type=CouponType.FREE_SHIPPING, min_subtotal=50_000
    )
    quote = checkout(
        [LineItem(sku="tat", unit_price=100_000, quantity=1, weight_g=1000)],
        CustomerTier.PLUS,
        ShippingZone.DOMESTIC,
        PaymentMethod.CARD,
        coupon,
    )
    assert quote.shipping == 0
    assert quote.total == 98_455


def test_gio_rong_bi_tu_choi():
    with pytest.raises(CartError):
        checkout([], CustomerTier.STANDARD, ShippingZone.DOMESTIC, PaymentMethod.CARD)


def test_breakdown_co_du_cac_khoan():
    quote = checkout(
        standard_items(),
        CustomerTier.STANDARD,
        ShippingZone.DOMESTIC,
        PaymentMethod.CARD,
    )
    assert set(quote.breakdown) == {
        "goods",
        "tier_discount",
        "coupon_discount",
        "shipping",
        "surcharge",
    }
