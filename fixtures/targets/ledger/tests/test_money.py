"""Kiểm thử chuẩn hoá và hiển thị số tiền."""

import pytest

from ledger.money import MoneyError, apply_delta, format_amount, normalize_amount


def test_nhan_so_nguyen():
    assert normalize_amount(150_000) == 150_000


def test_nhan_chuoi_so_nguyen():
    assert normalize_amount("150000") == 150_000


def test_tu_choi_so_khong_va_so_am():
    with pytest.raises(MoneyError):
        normalize_amount(0)
    with pytest.raises(MoneyError):
        normalize_amount(-5)


def test_tu_choi_bool_va_float():
    with pytest.raises(MoneyError):
        normalize_amount(True)
    with pytest.raises(MoneyError):
        normalize_amount(1.5)


def test_tu_choi_chuoi_khong_phai_so():
    with pytest.raises(MoneyError):
        normalize_amount("150k")


def test_apply_delta_cong_tru():
    assert apply_delta(1000, 500) == 1500
    assert apply_delta(1000, -1500) == -500


def test_format_amount():
    assert format_amount(1_234_567) == "1.234.567đ"
    assert format_amount(-1_234_567) == "-1.234.567đ"
