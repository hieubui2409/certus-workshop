"""Kiểm thử máy ghi sổ.

Ghi chú của đội: sổ có chạy song song nên chúng tôi có kiểm cả đường
`post_batch` ở chế độ chia theo tài khoản. Kết quả ổn định qua hàng nghìn lần
chạy CI.
"""

import pytest

from ledger.accounts import AccountBook
from ledger.engine import InsufficientFundsError, Interleaving, LedgerEngine
from ledger.entries import credit, debit


def make_engine(*account_ids, opening=0):
    book = AccountBook()
    for account_id in account_ids:
        book.open_account(account_id, opening_balance=opening)
    return LedgerEngine(book)


def test_ghi_mot_but_toan_credit():
    engine = make_engine("acc-1")
    assert engine.post(credit("acc-1", 1000)) == 1000
    assert engine.snapshot() == {"acc-1": 1000}


def test_ghi_lien_tiep_cong_don():
    engine = make_engine("acc-1")
    engine.post_many([credit("acc-1", 1000), credit("acc-1", 500), debit("acc-1", 200)])
    assert engine.snapshot()["acc-1"] == 1300
    assert engine.journal_size() == 3


def test_tu_choi_but_toan_lam_am_so_du():
    engine = make_engine("acc-1", opening=100)
    with pytest.raises(InsufficientFundsError):
        engine.post(debit("acc-1", 500))
    assert engine.snapshot()["acc-1"] == 100
    assert engine.journal_size() == 0


def test_tai_khoan_bu_tru_duoc_phep_am():
    book = AccountBook()
    book.open_account("acc-clearing", allow_negative=True)
    engine = LedgerEngine(book)
    assert engine.post(debit("acc-clearing", 500)) == -500


def test_history_loc_theo_tai_khoan():
    engine = make_engine("acc-1", "acc-2")
    engine.post_many([credit("acc-1", 100), credit("acc-2", 200), credit("acc-1", 300)])
    records = engine.history("acc-1")
    assert [r.balance_after for r in records] == [100, 400]


def test_post_batch_tuan_tu_cho_dung_tong():
    engine = make_engine("acc-1")
    entries = [credit("acc-1", 1) for _ in range(500)]
    engine.post_batch(entries, mode=Interleaving.SEQUENTIAL)
    assert engine.snapshot()["acc-1"] == 500


def test_post_batch_chia_theo_tai_khoan_chay_song_song():
    engine = make_engine("acc-1", "acc-2", "acc-3")
    entries = []
    for account_id in ("acc-1", "acc-2", "acc-3"):
        entries.extend(credit(account_id, 1) for _ in range(300))

    engine.post_batch(entries, mode=Interleaving.CONCURRENT_SHARDED)

    assert engine.snapshot() == {"acc-1": 300, "acc-2": 300, "acc-3": 300}
    assert engine.journal_size() == 900


def test_post_batch_nhieu_luong_ghi_du_so_dong_nhat_ky():
    engine = make_engine("acc-1")
    entries = [credit("acc-1", 1) for _ in range(400)]

    engine.post_batch(entries, mode=Interleaving.CONCURRENT_SHARED, workers=2)

    assert engine.journal_size() == 400


def test_ghi_vao_tai_khoan_khong_ton_tai():
    engine = make_engine("acc-1")
    with pytest.raises(KeyError):
        engine.post(credit("acc-999", 100))
