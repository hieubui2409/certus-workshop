"""Phí vận chuyển: phí nền theo vùng + phí theo cân nặng, có ngưỡng miễn phí."""

from __future__ import annotations

import math
from typing import Iterable

from .enums import CouponType, CustomerTier, ShippingZone
from .pricing import CartError, Coupon, LineItem

#: Phí nền cho ki-lô-gam đầu tiên.
BASE_FEE: dict[ShippingZone, int] = {
    ShippingZone.DOMESTIC: 20_000,
    ShippingZone.REGIONAL: 45_000,
    ShippingZone.INTERNATIONAL: 120_000,
}

#: Phí cho mỗi ki-lô-gam kể từ ki-lô-gam thứ hai.
PER_KG_FEE: dict[ShippingZone, int] = {
    ShippingZone.DOMESTIC: 5_000,
    ShippingZone.REGIONAL: 12_000,
    ShippingZone.INTERNATIONAL: 40_000,
}

#: Ngưỡng tiền hàng để được miễn phí ship. VIP luôn được miễn (ngưỡng 0).
FREE_SHIPPING_THRESHOLD: dict[CustomerTier, int] = {
    CustomerTier.STANDARD: 500_000,
    CustomerTier.PLUS: 300_000,
    CustomerTier.VIP: 0,
}

#: Giới hạn cân nặng cho một kiện đi quốc tế.
MAX_INTERNATIONAL_KG = 20


def billable_weight_kg(items: Iterable[LineItem]) -> int:
    """Cân nặng tính phí: làm tròn lên, tối thiểu 1 kg."""
    grams = sum(item.weight_g * item.quantity for item in items)
    return max(1, math.ceil(grams / 1000))


def applies_free_shipping(amount: int, coupon: Coupon) -> bool:
    """Mã loại FREE_SHIPPING có hiệu lực khi đơn đạt ngưỡng tối thiểu của mã."""
    if coupon.type is not CouponType.FREE_SHIPPING:
        return False
    return amount >= coupon.min_subtotal


def shipping_fee(
    items: Iterable[LineItem],
    zone: ShippingZone,
    tier: CustomerTier,
    amount: int,
    coupon: Coupon,
) -> int:
    """Phí ship cuối cùng cho một đơn."""
    items = list(items)
    if applies_free_shipping(amount, coupon):
        return 0
    if amount >= FREE_SHIPPING_THRESHOLD[tier]:
        return 0

    kilos = billable_weight_kg(items)
    if zone is ShippingZone.INTERNATIONAL and kilos > MAX_INTERNATIONAL_KG:
        raise CartError(
            f"kiện {kilos}kg vượt giới hạn {MAX_INTERNATIONAL_KG}kg cho tuyến quốc tế"
        )
    return BASE_FEE[zone] + PER_KG_FEE[zone] * (kilos - 1)
