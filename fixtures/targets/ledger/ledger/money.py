"""Số tiền trong sổ.

Quy ước: mọi số tiền là **số nguyên đồng**. Không có float ở bất cứ đâu trong
đường đi của tiền — float chỉ xuất hiện khi in ra cho người đọc.
"""

from __future__ import annotations


class MoneyError(ValueError):
    """Số tiền không hợp lệ."""


def normalize_amount(value: int) -> int:
    """Chuẩn hoá một số tiền đầu vào.

    Chấp nhận `int`, và `str` chỉ khi chuỗi là số nguyên thuần. Từ chối mọi
    thứ khác — sổ kế toán không đoán ý người gọi.
    """
    if isinstance(value, bool):
        raise MoneyError("bool không phải số tiền")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str) and value.lstrip("-").isdigit():
        amount = int(value)
    else:
        raise MoneyError(f"không đọc được số tiền: {value!r}")
    if amount <= 0:
        raise MoneyError("số tiền phải > 0")
    return amount


def apply_delta(balance: int, delta: int) -> int:
    """Số dư mới sau khi cộng một biến động. Hàm thuần, không đụng trạng thái."""
    return balance + delta


def format_amount(amount: int) -> str:
    """-1234567 -> '-1.234.567đ'."""
    sign = "-" if amount < 0 else ""
    return sign + f"{abs(amount):,}".replace(",", ".") + "đ"
