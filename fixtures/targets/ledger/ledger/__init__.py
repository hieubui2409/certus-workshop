"""ledger — sổ kế toán nhỏ, có đường ghi song song.

Repo mẫu LÀNH MẠNH: không có lỗi chủ đích, không có payload nào. Nó có đúng
một khiếm khuyết kỹ thuật **thật** — loại khiếm
khuyết mà mọi dự án có concurrency đều từng dính, và mọi công cụ đo theo dòng
đều bỏ sót. Xem `README.md`.
"""

from .accounts import Account, AccountBook, UnknownAccountError
from .engine import (
    InsufficientFundsError,
    Interleaving,
    JournalRecord,
    LedgerEngine,
)
from .entries import Entry, EntryType, credit, debit, signed_amount
from .money import MoneyError, format_amount, normalize_amount

__all__ = [
    "Account",
    "AccountBook",
    "UnknownAccountError",
    "InsufficientFundsError",
    "Interleaving",
    "JournalRecord",
    "LedgerEngine",
    "Entry",
    "EntryType",
    "credit",
    "debit",
    "signed_amount",
    "MoneyError",
    "format_amount",
    "normalize_amount",
]
