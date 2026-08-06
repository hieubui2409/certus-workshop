"""Các trục biến thiên của nghiệp vụ giỏ hàng.

Mỗi enum ở đây là một chiều mà giá cuối cùng phụ thuộc vào. Đây cũng là chỗ
CERTUS phân giải `ref` khi nhận một axis: `shopcart/enums.py::CustomerTier`.
Không khai lại các enum này ở module khác.
"""

from __future__ import annotations

from enum import Enum


class CustomerTier(Enum):
    """Hạng khách hàng — quyết định mức giảm giá nền và ngưỡng miễn phí ship."""

    STANDARD = "standard"
    PLUS = "plus"
    VIP = "vip"


class ShippingZone(Enum):
    """Vùng giao hàng — quyết định phí nền và phí theo cân nặng."""

    DOMESTIC = "domestic"
    REGIONAL = "regional"
    INTERNATIONAL = "international"


class PaymentMethod(Enum):
    """Phương thức thanh toán — quyết định phụ phí và ràng buộc theo vùng."""

    CARD = "card"
    WALLET = "wallet"
    COD = "cod"


class CouponType(Enum):
    """Loại mã giảm giá.

    `FREE_SHIPPING` cố ý không giảm tiền hàng: nó chỉ tác động lên phí ship,
    nên phần xử lý nằm ở `shipping.py` chứ không ở `pricing.py`.
    """

    NONE = "none"
    PERCENT = "percent"
    FIXED = "fixed"
    FREE_SHIPPING = "free_shipping"
