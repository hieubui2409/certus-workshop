"""Kiểm thử danh mục tài khoản."""

import pytest

from ledger.accounts import AccountBook, UnknownAccountError


def test_mo_tai_khoan_va_lay_lai():
    book = AccountBook()
    book.open_account("acc-1", opening_balance=1000)
    assert book.get("acc-1").balance == 1000


def test_tu_choi_mo_trung_tai_khoan():
    book = AccountBook()
    book.open_account("acc-1")
    with pytest.raises(ValueError):
        book.open_account("acc-1")


def test_lay_tai_khoan_khong_ton_tai():
    book = AccountBook()
    with pytest.raises(UnknownAccountError):
        book.get("acc-404")


def test_liet_ke_tai_khoan_theo_thu_tu():
    book = AccountBook()
    book.open_account("acc-2")
    book.open_account("acc-1")
    assert book.ids() == ["acc-1", "acc-2"]


def test_co_the_cho_phep_so_du_am():
    book = AccountBook()
    account = book.open_account("acc-clearing", allow_negative=True)
    assert account.allow_negative is True
