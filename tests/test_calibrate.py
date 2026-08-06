"""Ghim hành vi của `core/exec/calibrate.py`.

Hai luật bị ghim ở đây:

1. **Thứ tự sinh seed** — hash sổ TRƯỚC, mint nonce SAU. Đảo lại là lỗ
   "predictable before the fact" (RTB-4).
2. **Tỉ lệ trơ trọi bị cấm** — `false_high_rate` luôn kèm Wilson, và `total==0`
   cho `None` chứ không cho `0.0`.
"""

from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.types import Interval  # noqa: E402
from app.core.exec.calibrate import (  # noqa: E402
    CalibrationSeed,
    false_high_rate,
    false_high_verdict,
    ledger_digest,
    open_calibration,
    reopen_calibration,
    sample_mutants,
)
from app.core.exec.mutate import MutationRun  # noqa: E402
from app.core.exec.runner import ExecConfig, load_exec_config  # noqa: E402

LEDGER = [
    '{"claim_id":"c1","exit_code":0,"verdict":"executed-pass"}',
    '{"claim_id":"c2","exit_code":1,"verdict":"executed-fail"}',
]


@pytest.fixture
def cfg() -> ExecConfig:
    return load_exec_config(reload=True)


def _run(
    result: str,
    *,
    in_force: bool = True,
    mutant_id: str = "pkg/mod.py::x_add__mutmut_1",
) -> MutationRun:
    return MutationRun(
        mutant_id=mutant_id,
        seed_id="seed",
        result=result,  # type: ignore[arg-type]
        bound=in_force,
        file="pkg/mod.py",
        line=4,
        mutant_in_force=in_force,
        exit_code=0 if result == "survived" else 1,
        status=result,
        tests_touching=1 if in_force else 0,
    )


def _fake_interval(*, k: int, n: int, conf: float, method: str) -> Interval:
    """Wilson giả, biên rộng có chủ ý — test ở đây kiểm MỐI NỐI, không kiểm toán.

    Toán thật thuộc app/core/stats/intervals.py và có test riêng ở đó.
    """
    half = 0.5 / n
    p = k / n
    return Interval(
        lower=max(0.0, p - half),
        upper=min(1.0, p + half),
        conf=conf,
        method=method,  # type: ignore[arg-type]
        n=n,
        k=k,
        saturated=p in (0.0, 1.0),
    )


# ── seed ────────────────────────────────────────────────────────────────


def test_digest_is_over_the_ledger_as_it_sits(cfg: ExecConfig) -> None:
    digest, count = ledger_digest(LEDGER)
    expected = hashlib.sha256("\n".join(LEDGER).encode("utf-8") + b"\n").hexdigest()
    assert digest == expected
    assert count == 2


def test_digest_reports_how_many_lines_it_hashed() -> None:
    """Băm 0 dòng và băm 4000 dòng cho ra hai chuỗi trông giống hệt nhau."""
    assert ledger_digest([])[1] == 0
    assert ledger_digest(LEDGER)[1] == 2


def test_digest_is_taken_before_the_nonce_exists() -> None:
    """Nonce KHÔNG được ảnh hưởng tới thứ đang bị hash.

    Nếu thứ tự bị đảo, digest của hai lượt mở trên cùng một sổ sẽ khác nhau —
    và bên viết probe tính trước được danh sách ô sắp bị kiểm.
    """
    first = open_calibration(LEDGER)
    second = open_calibration(LEDGER)

    assert first.ledger_closed_digest == second.ledger_closed_digest
    assert first.ledger_closed_digest == ledger_digest(LEDGER)[0]
    assert first.calib_nonce != second.calib_nonce
    assert first.calib_seed != second.calib_seed


def test_seed_is_the_hash_of_digest_then_nonce() -> None:
    seed = open_calibration(LEDGER)
    expected = hashlib.sha256(
        (seed.ledger_closed_digest + seed.calib_nonce).encode("utf-8")
    ).hexdigest()
    assert seed.calib_seed == expected


def test_nonce_comes_from_secrets_and_has_full_width() -> None:
    seed = open_calibration(LEDGER)
    assert len(seed.calib_nonce) == 32
    int(seed.calib_nonce, 16)  # nổ nếu không phải hex


def test_no_door_exists_for_passing_a_nonce_in() -> None:
    """Một cửa để truyền nonce từ ngoài là một cửa để bên bị chấm chọn nonce."""
    params = inspect.signature(open_calibration).parameters
    assert list(params) == ["ledger_lines"]


def test_a_closed_round_can_be_verified_again() -> None:
    seed = open_calibration(LEDGER)
    again = reopen_calibration(seed.ledger_closed_digest, seed.calib_nonce)
    assert again.calib_seed == seed.calib_seed


def test_a_changed_ledger_changes_the_digest() -> None:
    a, _ = ledger_digest(LEDGER)
    b, _ = ledger_digest([*LEDGER, '{"claim_id":"c3"}'])
    assert a != b


# ── false_high_rate ─────────────────────────────────────────────────────


def test_empty_denominator_is_none_not_zero(cfg: ExecConfig) -> None:
    """0.0 nghĩa là "đã đo, không mutant nào sống". None nghĩa là "chưa đo được"."""
    measured = false_high_rate([], config=cfg, interval_fn=_fake_interval)
    assert measured.rate is None
    assert measured.interval is None
    assert "empty-denominator" in measured.flags


def test_rate_is_survived_over_total(cfg: ExecConfig) -> None:
    runs = [_run("survived"), _run("survived"), _run("killed"), _run("killed")]
    measured = false_high_rate(runs, config=cfg, interval_fn=_fake_interval)
    assert measured.survived == 2
    assert measured.killed == 2
    assert measured.total == 4
    assert measured.rate == 0.5


def test_every_rate_carries_an_interval(cfg: ExecConfig) -> None:
    measured = false_high_rate([_run("killed")], config=cfg, interval_fn=_fake_interval)
    assert measured.interval is not None
    assert measured.interval.n == 1
    assert measured.interval.conf == cfg.calibration.conf
    assert measured.interval.method == cfg.calibration.interval_method


def test_mutants_that_never_ran_are_excluded_visibly(cfg: ExecConfig) -> None:
    """Loại trừ phải NHÌN THẤY được, không được hấp thụ im lặng."""
    runs = [_run("killed"), _run("survived", in_force=False)]
    measured = false_high_rate(runs, config=cfg, interval_fn=_fake_interval)
    assert measured.total == 1
    assert measured.excluded_unresolved == 1
    assert measured.rate == 0.0


def test_all_mutants_out_of_force_reads_as_no_measurement(cfg: ExecConfig) -> None:
    """Đây đúng là ca `0.0` nguy hiểm nhất của DEBTS O1."""
    runs = [_run("survived", in_force=False), _run("killed", in_force=False)]
    measured = false_high_rate(runs, config=cfg, interval_fn=_fake_interval)
    assert measured.rate is None
    assert measured.excluded_unresolved == 2


def test_small_sample_is_flagged(cfg: ExecConfig) -> None:
    measured = false_high_rate([_run("survived")], config=cfg, interval_fn=_fake_interval)
    assert "n-too-small" in measured.flags
    assert "saturated" in measured.flags


# ── verdict ─────────────────────────────────────────────────────────────


def test_the_debts_case_rate_one_on_two_samples_still_blocks(cfg: ExecConfig) -> None:
    """`{"killed": 0, "survived": 2, "rate": 1.0}` — bản ghi gốc của DEBTS M1.

    Ngay cả biên DƯỚI của một mẫu 2/2 cũng đã vượt ngưỡng, nên verdict là
    `block` và cổng chặn đúng. Wilson không nới cái cổng này ra; nó chỉ nói
    thêm rằng khoảng còn rất rộng.
    """
    runs = [_run("survived"), _run("survived")]
    measured = false_high_rate(runs, config=cfg, interval_fn=_fake_interval)
    assert measured.rate == 1.0
    assert false_high_verdict(measured, config=cfg) == "block"


def test_a_clean_small_sample_does_not_earn_a_pass(cfg: ExecConfig) -> None:
    """Đây mới là chỗ Wilson đổi kết luận, và là chỗ tài liệu gốc thiếu.

    `{"killed": 2, "survived": 0, "rate": 0.0}` đọc như "hoàn hảo" nếu chỉ nhìn
    điểm ước lượng — 0.0 nằm dưới ngưỡng 0.15, cổng cho qua. Nhưng biên TRÊN
    của 0/2 còn cao hơn ngưỡng rất nhiều: cỡ mẫu này không loại trừ nổi một
    tỉ lệ chấm-cao-sai tệ hại. Verdict đúng là `inconclusive`, và
    `inconclusive` KHÔNG phải `pass`.
    """
    runs = [_run("killed"), _run("killed")]
    measured = false_high_rate(runs, config=cfg, interval_fn=_fake_interval)
    assert measured.rate == 0.0
    assert measured.rate < cfg.calibration.false_high_block
    assert false_high_verdict(measured, config=cfg) == "inconclusive"


def test_no_measurement_is_never_a_pass(cfg: ExecConfig) -> None:
    measured = false_high_rate([], config=cfg, interval_fn=_fake_interval)
    assert false_high_verdict(measured, config=cfg) == "inconclusive"


def test_verdict_uses_the_bounds_not_the_point_estimate(cfg: ExecConfig) -> None:
    threshold = cfg.calibration.false_high_block

    def wide(*, k: int, n: int, conf: float, method: str) -> Interval:
        return Interval(lower=threshold + 0.2, upper=1.0, conf=conf, method=method, n=n, k=k)

    def narrow(*, k: int, n: int, conf: float, method: str) -> Interval:
        return Interval(lower=0.0, upper=threshold, conf=conf, method=method, n=n, k=k)

    runs = [_run("survived"), _run("killed")]
    assert false_high_verdict(false_high_rate(runs, config=cfg, interval_fn=wide), config=cfg) == "block"
    assert (
        false_high_verdict(false_high_rate(runs, config=cfg, interval_fn=narrow), config=cfg)
        == "pass"
    )


# ── lấy mẫu ─────────────────────────────────────────────────────────────


def _seed() -> CalibrationSeed:
    return reopen_calibration("a" * 64, "b" * 32)


def test_sampling_is_reproducible_for_a_closed_seed() -> None:
    ids = [f"m{i}" for i in range(200)]
    first = sample_mutants(ids, seed=_seed(), rate=0.25)
    second = sample_mutants(ids, seed=_seed(), rate=0.25)
    assert first == second


def test_sampling_keeps_input_order() -> None:
    ids = [f"m{i}" for i in range(200)]
    chosen = sample_mutants(ids, seed=_seed(), rate=0.5)
    assert chosen == [i for i in ids if i in set(chosen)]


def test_a_different_seed_selects_a_different_subset() -> None:
    ids = [f"m{i}" for i in range(200)]
    a = sample_mutants(ids, seed=_seed(), rate=0.25)
    b = sample_mutants(ids, seed=reopen_calibration("c" * 64, "d" * 32), rate=0.25)
    assert a != b


def test_rate_zero_and_one_are_the_endpoints() -> None:
    ids = [f"m{i}" for i in range(50)]
    assert sample_mutants(ids, seed=_seed(), rate=0.0) == []
    assert sample_mutants(ids, seed=_seed(), rate=1.0) == ids


def test_rate_outside_the_unit_interval_is_refused() -> None:
    with pytest.raises(ValueError):
        sample_mutants(["m1"], seed=_seed(), rate=1.5)


def test_sampling_lands_near_the_requested_rate() -> None:
    ids = [f"m{i}" for i in range(2000)]
    chosen = sample_mutants(ids, seed=_seed(), rate=0.25)
    assert 0.20 <= len(chosen) / len(ids) <= 0.30


# ── mối nối với Wilson thật ─────────────────────────────────────────────


def test_the_real_wilson_module_is_the_one_that_gets_called(cfg: ExecConfig) -> None:
    """Không có bản Wilson thứ hai trong repo: mặc định phải resolve module thật."""
    pytest.importorskip(
        "app.core.stats.intervals", reason="SDD 01 chưa xong — mối nối được kiểm bằng inject"
    )
    runs = [_run("survived"), _run("killed"), _run("killed")]
    measured = false_high_rate(runs, config=cfg)
    assert measured.interval is not None
    assert measured.interval.n == 3
    assert measured.interval.lower <= measured.rate <= measured.interval.upper
