"""Máy ghi sổ: nhận bút toán, cập nhật số dư, ghi nhật ký.

Sổ này được nhiều luồng dùng chung (worker nạp tiền, worker đối soát, API),
nên `post_batch()` có sẵn chế độ chạy song song.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

from .accounts import AccountBook
from .entries import Entry, signed_amount
from .money import apply_delta


class InsufficientFundsError(ValueError):
    """Bút toán làm số dư âm trên tài khoản không cho phép âm."""


class Interleaving(Enum):
    """Cách một lô bút toán được đưa vào sổ.

    Đây là một trục biến thiên thật của hệ: cùng một lô bút toán, ba chế độ
    dưới đây đi qua cùng những dòng code nhưng theo thứ tự thi hành khác nhau.
    """

    SEQUENTIAL = "sequential"
    CONCURRENT_SHARDED = "concurrent_sharded"
    CONCURRENT_SHARED = "concurrent_shared"


@dataclass(frozen=True)
class JournalRecord:
    """Một dòng nhật ký, ghi lại số dư ngay sau bút toán."""

    entry: Entry
    balance_after: int


class LedgerEngine:
    """Ghi sổ cho một `AccountBook`."""

    def __init__(self, book: AccountBook) -> None:
        self._book = book
        self._journal: list[JournalRecord] = []
        self._lock = threading.Lock()

    # --- đường đi của một bút toán -------------------------------------

    def post(self, entry: Entry) -> int:
        """Ghi một bút toán, trả về số dư mới."""
        account = self._book.get(entry.account_id)
        current = account.balance
        new_balance = apply_delta(current, signed_amount(entry))
        if new_balance < 0 and not account.allow_negative:
            raise InsufficientFundsError(
                f"{entry.account_id}: số dư {current} không đủ cho bút toán {entry.amount}"
            )
        self._journal.append(JournalRecord(entry=entry, balance_after=new_balance))
        account.balance = new_balance
        return new_balance

    def post_many(self, entries: Iterable[Entry]) -> None:
        for entry in entries:
            self.post(entry)

    def post_batch(
        self,
        entries: Sequence[Entry],
        mode: Interleaving = Interleaving.SEQUENTIAL,
        workers: int = 2,
    ) -> None:
        """Đưa cả lô vào sổ theo chế độ `mode`."""
        if mode is Interleaving.SEQUENTIAL:
            self.post_many(entries)
            return

        shards = self._split(entries, workers, mode)
        threads = [
            threading.Thread(target=self.post_many, args=(shard,), daemon=True)
            for shard in shards
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    @staticmethod
    def _split(
        entries: Sequence[Entry], workers: int, mode: Interleaving
    ) -> list[list[Entry]]:
        """Chia lô cho các luồng.

        `CONCURRENT_SHARDED` gom theo tài khoản để mỗi luồng chỉ chạm tài khoản
        của mình; `CONCURRENT_SHARED` chia đều bất kể tài khoản.
        """
        if mode is Interleaving.CONCURRENT_SHARDED:
            by_account: dict[str, list[Entry]] = {}
            for entry in entries:
                by_account.setdefault(entry.account_id, []).append(entry)
            return list(by_account.values())
        return [list(entries[i::workers]) for i in range(workers)]

    # --- đọc trạng thái -------------------------------------------------

    def snapshot(self) -> dict[str, int]:
        """Ảnh chụp số dư mọi tài khoản."""
        with self._lock:
            return {
                account_id: self._book.get(account_id).balance
                for account_id in self._book.ids()
            }

    def journal_size(self) -> int:
        with self._lock:
            return len(self._journal)

    def history(self, account_id: str) -> list[JournalRecord]:
        with self._lock:
            return [r for r in self._journal if r.entry.account_id == account_id]
