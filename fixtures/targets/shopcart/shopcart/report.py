"""In bảng chiết tính ra chuỗi cho CLI và cho email xác nhận đơn."""

from __future__ import annotations

from .cart import Quote

CURRENCY_SUFFIX = "đ"


def format_money(amount: int) -> str:
    """1234567 -> '1.234.567đ'."""
    return f"{amount:,}".replace(",", ".") + CURRENCY_SUFFIX


def format_quote(quote: Quote, *, verbose: bool = False) -> str:
    """Bảng chiết tính dạng nhiều dòng."""
    lines = [
        f"Tiền hàng:     {format_money(quote.subtotal)}",
        f"Giảm giá:      -{format_money(quote.discount)}",
        f"Phí vận chuyển:{format_money(quote.shipping)}",
        f"Phụ phí:       {format_money(quote.surcharge)}",
        f"Tổng cộng:     {format_money(quote.total)}",
    ]
    if verbose:
        lines.append("--- chi tiết ---")
        for key, value in sorted(quote.breakdown.items()):
            lines.append(f"{key}: {format_money(value)}")
    return "\n".join(lines)


def format_receipt_email(quote: Quote, customer_name: str) -> str:
    """Thân email xác nhận đơn."""
    greeting = f"Chào {customer_name},"
    if quote.discount > 0:
        note = f"Bạn đã tiết kiệm {format_money(quote.discount)} cho đơn này."
    else:
        note = "Đơn này chưa áp dụng khuyến mãi nào."
    return "\n\n".join([greeting, format_quote(quote), note])
