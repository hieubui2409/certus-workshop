"""Hiệu chuẩn: sinh seed cho vòng kiểm, và đo `false_high_rate` kèm Wilson.

Đây là chỗ trả lời câu hỏi *"cả cỗ máy này có đáng tin không"*. Hai thứ sống ở
đây và cả hai đều dễ làm sai theo kiểu không ai thấy:

1. **Thứ tự sinh seed** — hash sổ TRƯỚC, mint nonce SAU. Đảo lại là lỗ
   "predictable before the fact".
2. **`false_high_rate` kèm khoảng tin cậy** — một tỉ lệ trơ trọi trên cỡ mẫu 2
   không nói được gì, nhưng nó ĐỌC như một kết luận.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.contracts.types import Interval
from app.core.exec.mutate import MutationRun
from app.core.exec.runner import ExecConfig, load_exec_config

#: Hàm tính khoảng tin cậy. Kiểu này tồn tại để `false_high_rate()` tiêm được
#: bản Wilson thật vào mà không import cứng — KHÔNG phải để có bản Wilson thứ
#: hai trong repo. Chỉ có đúng một cài đặt: app/core/stats/intervals.py.
IntervalFn = Callable[..., Interval]


@dataclass(frozen=True)
class CalibrationSeed:
    """Kết quả của `calibrate --open`. Bất biến sau khi đóng sổ."""

    ledger_closed_digest: str
    calib_nonce: str
    calib_seed: str
    records_closed: int


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ledger_digest(ledger_lines: Iterable[str]) -> tuple[str, int]:
    """Băm sổ bằng chứng NHƯ NÓ ĐANG NẰM, kèm số dòng đã băm.

    Trả về cả số dòng vì một digest không nói được nó đã băm bao nhiêu thứ, và
    "băm 0 dòng" với "băm 4000 dòng" cho ra hai chuỗi trông giống hệt nhau.
    """
    hasher = hashlib.sha256()
    count = 0
    for line in ledger_lines:
        hasher.update(line.rstrip("\n").encode("utf-8"))
        hasher.update(b"\n")
        count += 1
    return hasher.hexdigest(), count


def open_calibration(ledger_lines: Iterable[str]) -> CalibrationSeed:
    """Mở một vòng hiệu chuẩn. THỨ TỰ BA BƯỚC DƯỚI ĐÂY LÀ LOAD-BEARING.

        ledger_closed_digest = sha256( mọi dòng ledger tính tới lúc đóng sổ )
        calib_nonce          = secrets.token_hex(16)     # SAU khi hash
        calib_seed           = sha256( digest || nonce )

    Vì sao thứ tự quan trọng, chứ không phải "cho gọn":

    * Băm sổ TRƯỚC nghĩa là nội dung được băm đã cố định trước khi có bất kỳ
      thứ gì ngẫu nhiên. Nếu mint nonce trước, nonce lọt được vào thứ sắp bị
      băm, và người viết probe TÍNH TRƯỚC được danh sách ô sắp bị kiểm. Đó
      đúng là lỗ `RTB-4` mà bản v2 của tài liệu nền để lại với `seed = hash(grid)`
      — `grid.json` nằm trên đĩa và model ĐỌC ĐƯỢC (chỉ bị cấm ghi).
    * Nonce do CHÍNH bước này sinh, bằng `secrets`, **0 lời gọi model**. Hàm cố
      ý KHÔNG có tham số nonce: một cửa để truyền nonce từ ngoài vào là một cửa
      để bên bị chấm chọn nonce.
    * Seed phụ thuộc cả hai nên tái lập được sau khi đã đóng sổ, mà không đoán
      trước được lúc sổ còn mở.
    """
    digest, count = ledger_digest(ledger_lines)
    calib_nonce = secrets.token_hex(16)
    calib_seed = _sha256_hex((digest + calib_nonce).encode("utf-8"))
    return CalibrationSeed(
        ledger_closed_digest=digest,
        calib_nonce=calib_nonce,
        calib_seed=calib_seed,
        records_closed=count,
    )


def reopen_calibration(digest: str, nonce: str, records_closed: int = 0) -> CalibrationSeed:
    """Dựng lại một seed đã đóng sổ từ digest + nonce đã lưu.

    Dùng để kiểm chứng lại một vòng cũ. Không dùng để MỞ vòng mới — mở vòng mới
    bằng nonce có sẵn là đúng thứ `open_calibration()` từ chối cho làm.
    """
    return CalibrationSeed(
        ledger_closed_digest=digest,
        calib_nonce=nonce,
        calib_seed=_sha256_hex((digest + nonce).encode("utf-8")),
        records_closed=records_closed,
    )


# ──────────────────────────────────────────────────────────────────────────
# false_high_rate
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FalseHighRate:
    """`survived / total` — tỉ lệ CHẤM-CAO-SAI.

    ⚠ Đọc kỹ chiều của con số này. `rate = 1.0` là trường hợp TỆ NHẤT có thể,
    KHÔNG phải "bắt được 100%". Bản ghi gốc trong DEBTS.md mục M1:
    `{"killed": 0, "survived": 2, "rate": 1.0}` — mọi mutant đều sống sót, và
    cổng chặn đúng vì lẽ đó.

    `rate is None` khi `total == 0`. Không phải 0.0: 0.0 nghĩa là "đã đo, không
    mutant nào sống", ngược hẳn với "chưa đo được mutant nào".
    """

    killed: int
    survived: int
    total: int
    rate: float | None
    interval: Interval | None
    flags: list[str] = field(default_factory=list)
    excluded_unresolved: int = 0


def _default_interval_fn() -> IntervalFn:
    """Lấy hàm Wilson thật. Không có thì NỔ, không có bản dự phòng tự viết.

    Một bản Wilson thứ hai "tạm dùng cho tới khi module kia xong" là cách kinh
    điển để hai nửa hệ thống báo hai con số khác nhau cho cùng dữ liệu.
    """
    from app.core.stats.intervals import interval

    return interval


def false_high_rate(
    runs: Sequence[MutationRun],
    *,
    config: ExecConfig | None = None,
    interval_fn: IntervalFn | None = None,
    require_in_force: bool = True,
) -> FalseHighRate:
    """Tính tỉ lệ chấm-cao-sai trên các mutation run, kèm Wilson interval.

    `require_in_force=True` loại các run không chứng minh được mutant đã thật
    sự chạy. Đây là hệ quả trực tiếp của DEBTS O1: ba con số rỗng liên tiếp cho
    cùng một phép đo, và lần nguy hiểm nhất là `0.0` — *"đọc y hệt oracle mù
    hoàn toàn, sự thật là lỗi cấy chưa từng chạy một dòng"*. Số bị loại được
    trả về ở `excluded_unresolved` để người đọc THẤY nó, không phải để nó biến
    mất khỏi mẫu số trong im lặng.

    Wilson là bắt buộc, không phải trang trí: đây chính là mối nối mà tài liệu
    gốc thiếu, và là lý do `rate=1.0` trên `n=2` của nó không kết luận được gì.
    """
    cfg = config or load_exec_config()
    counted = [r for r in runs if r.mutant_in_force] if require_in_force else list(runs)
    excluded = len(runs) - len(counted)

    killed = sum(1 for r in counted if r.result == "killed")
    survived = sum(1 for r in counted if r.result == "survived")
    total = killed + survived

    if total == 0:
        return FalseHighRate(
            killed=0,
            survived=0,
            total=0,
            rate=None,
            interval=None,
            flags=["empty-denominator"],
            excluded_unresolved=excluded,
        )

    fn = interval_fn or _default_interval_fn()
    ci = fn(
        k=survived,
        n=total,
        conf=cfg.calibration.conf,
        method=cfg.calibration.interval_method,
    )

    flags: list[str] = []
    if total < cfg.calibration.min_sample_size:
        flags.append("n-too-small")
    if getattr(ci, "saturated", False):
        flags.append("saturated")

    return FalseHighRate(
        killed=killed,
        survived=survived,
        total=total,
        rate=survived / total,
        interval=ci,
        flags=flags,
        excluded_unresolved=excluded,
    )


FalseHighVerdict = Literal["block", "pass", "inconclusive"]


def false_high_verdict(
    measurement: FalseHighRate, *, config: ExecConfig | None = None
) -> FalseHighVerdict:
    """So `false_high_rate` với `calibration.false_high_block`, dùng BIÊN chứ
    không dùng điểm ước lượng.

    | điều kiện                        | verdict        |
    |----------------------------------|----------------|
    | biên dưới > ngưỡng               | block          |
    | biên trên <= ngưỡng              | pass           |
    | interval vắt ngang, hoặc rate None | inconclusive |

    `inconclusive` KHÔNG phải `pass`. Nó là câu "cỡ mẫu chưa nói được gì", và
    gate ở tầng trên phải xử nó như một lý do dừng. Đây đúng là ca `rate=1.0,
    n=2`: điểm ước lượng chạm trần, còn Wilson 95% cho khoảng rộng gần nửa
    thang đo — con số trung thực duy nhất là "chưa biết".
    """
    cfg = config or load_exec_config()
    threshold = cfg.calibration.false_high_block

    if measurement.rate is None or measurement.interval is None:
        return "inconclusive"
    if measurement.interval.lower > threshold:
        return "block"
    if measurement.interval.upper <= threshold:
        return "pass"
    return "inconclusive"


# ──────────────────────────────────────────────────────────────────────────
# Lấy mẫu theo seed
# ──────────────────────────────────────────────────────────────────────────


def sample_mutants(
    mutant_ids: Sequence[str],
    *,
    seed: CalibrationSeed,
    rate: float,
) -> list[str]:
    """Chọn một tập con xác định theo `calib_seed`.

    Dùng dòng hash sha256 chứ không `random.Random(seed)`: cả hai tái lập được
    trong CÙNG một bản CPython, nhưng chỉ dòng hash tái lập được QUA các bản
    build và độc lập với state của interpreter (`dst_scheduler.py:3-7`).

    Thứ tự trả về theo thứ tự đầu vào, không theo thứ hạng hash — để hai lượt
    chạy so được với nhau bằng mắt.
    """
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"rate phải nằm trong [0,1], nhận {rate}")
    if rate == 0.0 or not mutant_ids:
        return []

    cutoff = int(rate * (1 << 32))
    chosen: list[str] = []
    for mutant_id in mutant_ids:
        stream = _sha256_hex((seed.calib_seed + "|" + mutant_id).encode("utf-8"))
        if int(stream[:8], 16) < cutoff:
            chosen.append(mutant_id)
    return chosen


__all__ = [
    "CalibrationSeed",
    "FalseHighRate",
    "FalseHighVerdict",
    "IntervalFn",
    "false_high_rate",
    "false_high_verdict",
    "ledger_digest",
    "open_calibration",
    "reopen_calibration",
    "sample_mutants",
]
