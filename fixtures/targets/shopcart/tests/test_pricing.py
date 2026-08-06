"""Kiểm thử phần tiền hàng."""

import pytest

from shopcart.enums import CouponType, CustomerTier
from shopcart.pricing import (
    NO_COUPON,
    CartError,
    Coupon,
    LineItem,
    cap_discount,
    coupon_discount,
    subtotal,
    tier_discount,
)


def make_items():
    return [
        LineItem(sku="ao-thun", unit_price=150_000, quantity=2, weight_g=300),
        LineItem(sku="mu-luoi-trai", unit_price=100_000, quantity=1, weight_g=200),
    ]


def test_subtotal_cong_don_tung_dong():
    assert subtotal(make_items()) == 400_000


def test_line_item_tu_choi_so_luong_khong_duong():
    with pytest.raises(CartError):
        LineItem(sku="x", unit_price=1000, quantity=0).total()


def test_line_item_tu_choi_don_gia_am():
    with pytest.raises(CartError):
        LineItem(sku="x", unit_price=-1, quantity=1).total()


@pytest.mark.parametrize(
    "tier,expected",
    [
        (CustomerTier.STANDARD, 0),
        (CustomerTier.PLUS, 12_000),
        (CustomerTier.VIP, 28_000),
    ],
)
def test_tier_discount_theo_tung_hang(tier, expected):
    assert tier_discount(400_000, tier) == expected


def test_coupon_none_khong_giam():
    assert coupon_discount(400_000, NO_COUPON) == 0


def test_coupon_percent():
    coupon = Coupon(code="SALE10", type=CouponType.PERCENT, value=10)
    assert coupon_discount(400_000, coupon) == 40_000


def test_coupon_fixed_khong_vuot_tien_hang():
    coupon = Coupon(code="GIAM500K", type=CouponType.FIXED, value=500_000)
    assert coupon_discount(400_000, coupon) == 400_000


def test_coupon_duoi_nguong_toi_thieu_thi_khong_ap_dung():
    coupon = Coupon(
        code="SALE10", type=CouponType.PERCENT, value=10, min_subtotal=1_000_000
    )
    assert coupon_discount(400_000, coupon) == 0


def test_coupon_free_shipping_khong_dung_toi_tien_hang():
    coupon = Coupon(code="FREESHIP", type=CouponType.FREE_SHIPPING)
    assert coupon_discount(400_000, coupon) == 0


def test_cap_discount_ap_tran_mot_nua():
    assert cap_discount(400_000, 300_000) == 200_000
    assert cap_discount(400_000, 100_000) == 100_000
