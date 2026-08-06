"""Kiểm thử bút toán."""

import pytest

from ledger.entries import Entry, EntryType, credit, debit, signed_amount
from ledger.money import MoneyError


def test_credit_lam_tang_so_du():
    assert signed_amount(credit("acc-1", 1000)) == 1000


def test_debit_lam_giam_so_du():
    assert signed_amount(debit("acc-1", 1000)) == -1000


def test_entry_chuan_hoa_so_tien_chuoi():
    entry = Entry(account_id="acc-1", amount="2500", type=EntryType.CREDIT)
    assert entry.amount == 2500


def test_entry_tu_choi_so_tien_khong_hop_le():
    with pytest.raises(MoneyError):
        credit("acc-1", 0)


def test_entry_tu_choi_thieu_tai_khoan():
    with pytest.raises(ValueError):
        credit("", 1000)


def test_entry_giu_ref():
    assert credit("acc-1", 1000, ref="nap-tien-01").ref == "nap-tien-01"
