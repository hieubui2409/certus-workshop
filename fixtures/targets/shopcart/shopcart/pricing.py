"""Tiền hàng: tạm tính, giảm theo hạng khách, giảm theo mã, và trần giảm giá.

Mọi số tiền là số nguyên đồng (VND). Không dùng float để lưu tiền — chỉ dùng
float ở bước nhân tỉ lệ rồi làm tròn ngay về int.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .enums import CouponType, CustomerTier

#: Mức giảm nền theo hạng khách.
TIER_DISCOUNT_RATE: dict[CustomerTier, float] = {
    CustomerTier.STANDARD: 0.00,
    CustomerTier.PLUS: 0.03,
    CustomerTier.VIP: 0.07,
}

#: Tổng mọi khoản giảm không bao giờ vượt quá nửa giá trị đơn hàng.
MAX_TOTAL_DISCOUNT_RATE = 0.5


class CartError(ValueError):
    """Dữ liệu giỏ hàng không hợp lệ."""


@dataclass(frozen=True)
class LineItem:
    """Một dòng trong giỏ."""

    sku: str
    unit_price: int
    quantity: int
    weight_g: int = 500

    def total(self) -> int:
        if self.quantity <= 0:
            raise CartError(f"số lượng của {self.sku} phải > 0")
        if self.unit_price < 0:
            raise CartError(f"đơn giá của {self.sku} không được âm")
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Coupon:
    """Mã giảm giá.

    `value` mang nghĩa khác nhau tuỳ `type`: PERCENT thì là phần trăm,
    FIXED thì là số tiền đồng. FREE_SHIPPING bỏ qua `value`.
    """

    code: str
    type: CouponType
    value: int = 0
    min_subtotal: int = 0


#: Giỏ không dùng mã. Dùng hằng này thay vì None để tránh nhánh None ở mọi nơi.
NO_COUPON = Coupon(code="", type=CouponType.NONE)


def subtotal(items: Iterable[LineItem]) -> int:
    """Tổng tiền hàng trước mọi khoản giảm."""
    return sum(item.total() for item in items)


def tier_discount(amount: int, tier: CustomerTier) -> int:
    """Giảm giá nền theo hạng khách."""
    return round(amount * TIER_DISCOUNT_RATE[tier])


def coupon_discount(amount: int, coupon: Coupon) -> int:
    """Giảm giá theo mã, tính trên tiền hàng (không tính phí ship)."""
    if coupon.type is CouponType.NONE:
        return 0
    if amount < coupon.min_subtotal:
        return 0
    if coupon.type is CouponType.PERCENT:
        return round(amount * coupon.value / 100)
    if coupon.type is CouponType.FIXED:
        return min(coupon.value, amount)
    # FREE_SHIPPING không đụng tới tiền hàng — xem shipping.applies_free_shipping().
    return 0


def cap_discount(amount: int, discount: int) -> int:
    """Áp trần tổng giảm giá."""
    ceiling = round(amount * MAX_TOTAL_DISCOUNT_RATE)
    if discount > ceiling:
        return ceiling
    return discount
