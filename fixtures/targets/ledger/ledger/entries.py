"""Bút toán — đơn vị ghi sổ nhỏ nhất."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .money import normalize_amount


class EntryType(Enum):
    """Loại bút toán. CREDIT làm tăng số dư, DEBIT làm giảm."""

    DEBIT = "debit"
    CREDIT = "credit"


@dataclass(frozen=True)
class Entry:
    """Một bút toán đã được kiểm tra hợp lệ ngay lúc khởi tạo."""

    account_id: str
    amount: int
    type: EntryType
    ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", normalize_amount(self.amount))
        if not self.account_id:
            raise ValueError("bút toán phải có account_id")


def signed_amount(entry: Entry) -> int:
    """Biến động số dư mà bút toán này gây ra."""
    if entry.type is EntryType.CREDIT:
        return entry.amount
    return -entry.amount


def credit(account_id: str, amount: int, ref: str = "") -> Entry:
    return Entry(account_id=account_id, amount=amount, type=EntryType.CREDIT, ref=ref)


def debit(account_id: str, amount: int, ref: str = "") -> Entry:
    return Entry(account_id=account_id, amount=amount, type=EntryType.DEBIT, ref=ref)
