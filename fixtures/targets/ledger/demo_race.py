"""Chứng minh khiếm khuyết thứ tự thi hành của `LedgerEngine.post()`.

KHÔNG phải một ca kiểm thử — cố ý không đặt trong `tests/` và cố ý không đặt
tên `test_*.py`, vì bộ kiểm thử của repo mẫu phải xanh. Đây là kịch bản probe:
nó chạy hai (hoặc nhiều) luồng ghi vào **cùng một tài khoản** và đối chiếu số
dư thực tế với số dư đúng theo sổ nhật ký.

    python demo_race.py            # 4 luồng × 20000 bút toán, 5 vòng
    python demo_race.py 8 50000 3  # tự chọn luồng / bút toán / vòng

Vì sao mutation testing không bắt được: không dòng nào trong `post()` sai.
Đổi bất kỳ toán tử nào trong đó đều làm test tuần tự đỏ ngay. Cái sai là
**khoảng cách** giữa dòng đọc `account.balance` và dòng ghi `account.balance`.
"""

from __future__ import annotations

import sys
import threading

from ledger.accounts import AccountBook
from ledger.engine import Interleaving, LedgerEngine
from ledger.entries import credit


def run_once(workers: int, per_worker: int) -> tuple[int, int, int]:
    """Trả về (số dư kỳ vọng, số dư thực tế, số dòng nhật ký)."""
    book = AccountBook()
    book.open_account("acc-hot")
    engine = LedgerEngine(book)

    entries = [credit("acc-hot", 1) for _ in range(workers * per_worker)]
    engine.post_batch(entries, mode=Interleaving.CONCURRENT_SHARED, workers=workers)

    return len(entries), engine.snapshot()["acc-hot"], engine.journal_size()


def main(argv: list[str]) -> int:
    workers = int(argv[1]) if len(argv) > 1 else 4
    per_worker = int(argv[2]) if len(argv) > 2 else 20_000
    rounds = int(argv[3]) if len(argv) > 3 else 5

    print(
        f"Python {sys.version.split()[0]} · switch interval "
        f"{sys.getswitchinterval()}s · {workers} luồng × {per_worker} bút toán"
    )
    print(f"{'vòng':>5} {'kỳ vọng':>10} {'thực tế':>10} {'thiếu':>10} {'nhật ký':>10}")

    lost_rounds = 0
    for round_no in range(1, rounds + 1):
        expected, actual, journal = run_once(workers, per_worker)
        missing = expected - actual
        if missing != 0:
            lost_rounds += 1
        print(f"{round_no:>5} {expected:>10} {actual:>10} {missing:>10} {journal:>10}")

    print()
    print(f"Số vòng có mất bút toán: {lost_rounds}/{rounds}")
    print(
        "Chú ý: cột 'nhật ký' luôn đúng. Một bộ kiểm thử chỉ assert số dòng nhật ký\n"
        "sẽ XANH trong khi tiền đã bốc hơi — đó đúng là bộ kiểm thử hiện có ở\n"
        "tests/test_engine.py::test_post_batch_nhieu_luong_ghi_du_so_dong_nhat_ky."
    )
    return 0


if __name__ == "__main__":
    threading.stack_size(256 * 1024)
    raise SystemExit(main(sys.argv))
