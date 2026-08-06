"""Phụ phí và ràng buộc theo phương thức thanh toán."""

from __future__ import annotations

from .enums import PaymentMethod, ShippingZone

#: Phụ phí tính trên tổng phải trả (tiền hàng sau giảm + phí ship).
SURCHARGE_RATE: dict[PaymentMethod, float] = {
    PaymentMethod.CARD: 0.015,
    PaymentMethod.WALLET: 0.000,
    PaymentMethod.COD: 0.020,
}

#: Trần phụ phí một đơn, tránh phụ phí phình theo giá trị đơn.
SURCHARGE_CAP = 50_000

#: COD chỉ phục vụ tuyến trong nước.
COD_ZONES = frozenset({ShippingZone.DOMESTIC})

#: Trần giá trị đơn cho COD.
COD_MAX_AMOUNT = 5_000_000


class UnsupportedPaymentError(ValueError):
    """Phương thức thanh toán không dùng được cho đơn này."""


def is_supported(method: PaymentMethod, zone: ShippingZone) -> bool:
    """Phương thức có phục vụ vùng này không."""
    if method is PaymentMethod.COD:
        return zone in COD_ZONES
    return True


def validate_payment(method: PaymentMethod, zone: ShippingZone, amount: int) -> None:
    """Ném lỗi nếu cặp (phương thức, vùng, giá trị đơn) không hợp lệ."""
    if not is_supported(method, zone):
        raise UnsupportedPaymentError(
            f"{method.value} không phục vụ tuyến {zone.value}"
        )
    if method is PaymentMethod.COD and amount > COD_MAX_AMOUNT:
        raise UnsupportedPaymentError(
            f"đơn COD tối đa {COD_MAX_AMOUNT} đồng, đơn này {amount} đồng"
        )


def payment_fee(method: PaymentMethod, amount: int) -> int:
    """Phụ phí thanh toán, đã áp trần."""
    fee = round(amount * SURCHARGE_RATE[method])
    return min(fee, SURCHARGE_CAP)
