"""Kiểm thử phí vận chuyển."""

import pytest

from shopcart.enums import CouponType, CustomerTier, ShippingZone
from shopcart.pricing import NO_COUPON, CartError, Coupon, LineItem
from shopcart.shipping import applies_free_shipping, billable_weight_kg, shipping_fee


def items(weight_g: int, quantity: int = 1):
    return [
        LineItem(sku="hop", unit_price=10_000, quantity=quantity, weight_g=weight_g)
    ]


def test_billable_weight_lam_tron_len():
    assert billable_weight_kg(items(1200)) == 2


def test_billable_weight_toi_thieu_mot_kg():
    assert billable_weight_kg(items(50)) == 1


def test_phi_noi_dia_kg_dau_tien():
    fee = shipping_fee(
        items(800), ShippingZone.DOMESTIC, CustomerTier.STANDARD, 100_000, NO_COUPON
    )
    assert fee == 20_000


def test_phi_tang_theo_can_nang_tuyen_khu_vuc():
    fee = shipping_fee(
        items(2500), ShippingZone.REGIONAL, CustomerTier.STANDARD, 100_000, NO_COUPON
    )
    assert fee == 45_000 + 12_000 * 2


def test_mien_phi_khi_vuot_nguong_cua_hang_khach():
    fee = shipping_fee(
        items(800), ShippingZone.DOMESTIC, CustomerTier.STANDARD, 600_000, NO_COUPON
    )
    assert fee == 0


def test_ma_free_shipping_duoc_ap_dung():
    coupon = Coupon(code="FREESHIP", type=CouponType.FREE_SHIPPING, min_subtotal=50_000)
    assert applies_free_shipping(100_000, coupon) is True
    fee = shipping_fee(
        items(2500), ShippingZone.INTERNATIONAL, CustomerTier.STANDARD, 100_000, coupon
    )
    assert fee == 0


def test_ma_free_shipping_duoi_nguong_thi_van_tinh_phi():
    coupon = Coupon(
        code="FREESHIP", type=CouponType.FREE_SHIPPING, min_subtotal=500_000
    )
    assert applies_free_shipping(100_000, coupon) is False


def test_tuyen_quoc_te_tu_choi_kien_qua_nang():
    with pytest.raises(CartError):
        shipping_fee(
            items(1000, quantity=25),
            ShippingZone.INTERNATIONAL,
            CustomerTier.STANDARD,
            100_000,
            NO_COUPON,
        )
