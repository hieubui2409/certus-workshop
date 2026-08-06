"""Ghép mọi thứ lại: một hàm `checkout()` cho ra bảng chiết tính đầy đủ."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .enums import CustomerTier, PaymentMethod, ShippingZone
from .payment import payment_fee, validate_payment
from .pricing import NO_COUPON, CartError, Coupon, LineItem, cap_discount
from .pricing import coupon_discount, subtotal, tier_discount
from .shipping import shipping_fee


@dataclass(frozen=True)
class Quote:
    """Bảng chiết tính một đơn hàng."""

    subtotal: int
    discount: int
    shipping: int
    surcharge: int
    total: int
    breakdown: dict[str, int] = field(default_factory=dict)


def checkout(
    items: Iterable[LineItem],
    tier: CustomerTier,
    zone: ShippingZone,
    method: PaymentMethod,
    coupon: Coupon = NO_COUPON,
) -> Quote:
    """Tính tổng phải trả cho một đơn.

    Thứ tự là load-bearing: giảm giá tính trên tiền hàng, phí ship tính theo
    tiền hàng SAU giảm, phụ phí thanh toán tính trên (hàng + ship).
    """
    items = list(items)
    if not items:
        raise CartError("giỏ hàng rỗng")

    goods = subtotal(items)
    raw_discount = tier_discount(goods, tier) + coupon_discount(goods, coupon)
    discount = cap_discount(goods, raw_discount)
    payable_goods = goods - discount

    ship = shipping_fee(items, zone, tier, payable_goods, coupon)
    validate_payment(method, zone, payable_goods + ship)
    surcharge = payment_fee(method, payable_goods + ship)

    total = payable_goods + ship + surcharge
    return Quote(
        subtotal=goods,
        discount=discount,
        shipping=ship,
        surcharge=surcharge,
        total=total,
        breakdown={
            "goods": goods,
            "tier_discount": tier_discount(goods, tier),
            "coupon_discount": coupon_discount(goods, coupon),
            "shipping": ship,
            "surcharge": surcharge,
        },
    )
