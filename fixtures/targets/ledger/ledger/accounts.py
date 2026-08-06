"""Danh mục tài khoản."""

from __future__ import annotations

import threading
from dataclasses import dataclass


class UnknownAccountError(KeyError):
    """Không có tài khoản này trong sổ."""


@dataclass
class Account:
    """Một tài khoản. `balance` thay đổi theo thời gian nên đây không phải
    dataclass frozen."""

    id: str
    balance: int = 0
    allow_negative: bool = False


class AccountBook:
    """Kho tài khoản, khoá riêng cho thao tác mở tài khoản."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._lock = threading.Lock()

    def open_account(
        self, account_id: str, opening_balance: int = 0, allow_negative: bool = False
    ) -> Account:
        with self._lock:
            if account_id in self._accounts:
                raise ValueError(f"tài khoản {account_id} đã tồn tại")
            account = Account(
                id=account_id,
                balance=opening_balance,
                allow_negative=allow_negative,
            )
            self._accounts[account_id] = account
            return account

    def get(self, account_id: str) -> Account:
        try:
            return self._accounts[account_id]
        except KeyError:
            raise UnknownAccountError(account_id) from None

    def ids(self) -> list[str]:
        return sorted(self._accounts)
