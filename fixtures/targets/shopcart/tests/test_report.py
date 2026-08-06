"""Kiểm thử phần in ấn. Chỉ chạm đường đi chính — đủ cho nhu cầu hiện tại."""

from shopcart.cart import checkout
from shopcart.enums import CustomerTier, PaymentMethod, ShippingZone
from shopcart.pricing import LineItem
from shopcart.report import format_money, format_quote, format_receipt_email


def a_quote(tier=CustomerTier.PLUS):
    return checkout(
        [
            LineItem(sku="ao-thun", unit_price=150_000, quantity=2, weight_g=300),
            LineItem(sku="mu-luoi-trai", unit_price=100_000, quantity=1, weight_g=200),
        ],
        tier,
        ShippingZone.DOMESTIC,
        PaymentMethod.CARD,
    )


def test_format_money_dat_dau_cham_ngan():
    assert format_money(1_234_567) == "1.234.567đ"


def test_format_quote_co_du_nam_dong():
    text = format_quote(a_quote())
    assert len(text.splitlines()) == 5
    assert "Tổng cộng" in text


def test_email_nhac_so_tien_tiet_kiem():
    text = format_receipt_email(a_quote(), "Lan")
    assert text.startswith("Chào Lan,")
    assert "tiết kiệm" in text
