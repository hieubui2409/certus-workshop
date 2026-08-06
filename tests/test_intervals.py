"""Test cho `app.core.stats.intervals` — ba tầng, không thiếu tầng nào.

Vì sao ba tầng: tài liệu nền tự cảnh báo rằng các regression anchor do CHÍNH
probe đó sinh ra, nên chúng chỉ bắt được regression chứ không chứng minh công
thức đúng. Anchor một mình là một hình thức cargo cult khác.

    1. Regression anchor  — chép nguyên từ research note 01 §6
    2. Property test      — tính chất phải đúng với MỌI đầu vào, không chỉ vài cái
    3. Round-trip         — nghịch đảo phải trả về chính nó

Neo: docs/research-notes/01-confidence-intervals.md §6
     docs/design/sdd/01-core-stats.md §6
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from statistics import NormalDist

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.types import Interval  # noqa: E402
from app.core.stats.cluster import icc_anova  # noqa: E402
from app.core.stats.intervals import (  # noqa: E402
    METHODS,
    coverage,
    diff_newcombe,
    interval,
    interval_full,
    main,
    max_fails,
    mcnemar_wilson,
    min_n_all_pass,
    posterior_prob_ge,
    prior_from_evidence,
    z_for,
)
from app.core.stats.judge import judge_screen, rogan_gladen  # noqa: E402


def _bounds(k: int, n: int, conf: float = 0.95, method: str = "wilson") -> tuple[float, float]:
    iv = interval(k, n, conf=conf, method=method)
    return (iv.lower, iv.upper)


# ══════════════════════════ 1. REGRESSION ANCHOR ═══════════════════════════
# Chép từ note 01 §6. Dung sai 1e-6 cho anchor ghi đủ 6 chữ số; 1e-4 cho
# anchor mà tài liệu chỉ ghi 4 chữ số rồi đệm số 0 (0.442200, 0.963800...).


def test_anchor_wilson_8_of_10():
    """Ca trung tâm của cả workshop: "80% accuracy" thật ra là [0.49, 0.94]."""
    lower, upper = _bounds(8, 10)
    assert lower == pytest.approx(0.490162, abs=1e-6)
    assert upper == pytest.approx(0.943318, abs=1e-6)


def test_anchor_wilson_cc_8_of_10():
    lower, upper = _bounds(8, 10, method="wilson-cc")
    assert lower == pytest.approx(0.442200, abs=1e-4)
    assert upper == pytest.approx(0.964600, abs=1e-4)


def test_anchor_clopper_pearson_narrower_than_wilson_at_all_pass():
    """Ngược trực giác nhưng đo được: ở k=n, "exact" HẸP HƠN Wilson."""
    cp = interval(100, 100, method="clopper-pearson").lower
    wl = interval(100, 100, method="wilson").lower
    assert cp == pytest.approx(0.963800, abs=1e-4)
    assert wl == pytest.approx(0.963000, abs=1e-4)
    assert cp > wl


def test_anchor_jeffreys_10_of_10():
    assert interval(10, 10, method="jeffreys").lower == pytest.approx(0.782804, abs=1e-6)


def test_anchor_coverage_wilson():
    """Coverage THẬT của "Wilson 95%" không phải 95%."""
    assert coverage(10, 0.30, 0.95, "wilson") == pytest.approx(0.924403, abs=1e-5)
    assert coverage(10, 0.99, 0.95, "wilson") == pytest.approx(0.9044, abs=1e-4)


def test_anchor_min_n_all_pass_by_method():
    assert min_n_all_pass(0.95, method="wilson") == 73
    assert min_n_all_pass(0.95, method="clopper-pearson") == 72
    assert min_n_all_pass(0.95, method="jeffreys") == 49
    assert min_n_all_pass(0.95, method="wilson-cc") == 92


def test_anchor_min_n_table():
    """Bảng dán tường note 01 §4.4."""
    assert [min_n_all_pass(t) for t in (0.70, 0.80, 0.90, 0.95, 0.99)] == [9, 16, 35, 73, 381]


def test_anchor_all_pass_lower_bounds():
    """3/3 chỉ đảm bảo 43.9% — con số phá vỡ trực giác nhanh nhất."""
    expected = {
        1: 0.2065, 3: 0.4385, 5: 0.5655, 10: 0.7225, 20: 0.8389, 30: 0.8865,
        50: 0.9287, 73: 0.9500, 100: 0.9630, 200: 0.9812, 381: 0.9900, 500: 0.9924,
    }
    for n, lower in expected.items():
        assert interval(n, n).lower == pytest.approx(lower, abs=1e-4), f"n={n}"


def test_anchor_max_fails_table():
    """n=30 là BẤT KHẢ với T=0.90, kể cả 30/30 — None chứ không phải 0."""
    assert max_fails(30, 0.90) is None
    assert max_fails(50, 0.90) == 0
    assert max_fails(100, 0.90) == 4
    assert max_fails(200, 0.90) == 11
    assert max_fails(500, 0.90) == 36


def test_anchor_icc_anova():
    stats = icc_anova([(20, 20), (20, 20), (19, 20), (8, 20), (5, 20)])
    assert stats is not None
    assert stats["icc"] == pytest.approx(0.5619, abs=1e-4)


def test_anchor_diff_newcombe_overlapping_intervals_still_conclusive():
    """Chống lỗi đọc E2: hai interval CHỒNG NHAU mà vẫn kết luận được."""
    out = diff_newcombe(90, 100, 80, 100)
    assert out["lower"] == pytest.approx(0.0001, abs=1e-4)
    assert out["upper"] == pytest.approx(0.1995, abs=1e-4)
    assert out["conclusive"] is True
    # Hai interval riêng lẻ chồng nhau — đó chính là cái bẫy.
    assert out["interval_1"][0] < out["interval_2"][1]


def test_anchor_posterior_prob_ge():
    """30/30: Wilson lower 0.8865 FAIL nhưng P(p>=0.90) = 0.9884 PASS."""
    assert posterior_prob_ge(30, 30, 0.90) == pytest.approx(0.9884, abs=1e-4)
    assert interval(30, 30).lower < 0.90 < posterior_prob_ge(30, 30, 0.90)


def test_anchor_judge_screen_e23():
    """Dữ liệu THẬT từ E23 — thước này không đạt cổng."""
    out = judge_screen(TP=9, FN=4, TN=17, FP=5)
    assert out["youden_j"] == pytest.approx(0.4650, abs=1e-4)
    assert out["verdict"] == "rejected"
    assert out["error_amplification"] == pytest.approx(2.150, abs=1e-3)


def test_anchor_z_two_tailed_not_one_tailed():
    """2.33 là z MỘT phía của 99%; hai phía là 2.5758."""
    assert z_for(0.90) == pytest.approx(1.644854, abs=1e-6)
    assert z_for(0.95) == pytest.approx(1.959964, abs=1e-6)
    assert z_for(0.99) == pytest.approx(2.575829, abs=1e-6)


# ══════════════════════════ 2. PROPERTY TEST ═══════════════════════════════


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("k,n", [(0, 10), (1, 10), (5, 10), (8, 10), (10, 10), (46, 50), (3, 3)])
def test_property_monotone_in_conf(method, k, n):
    """Đòi chắc chắn hơn thì phải trả bằng interval rộng hơn. Không có ngoại lệ."""
    prev_lower, prev_upper = 1.0, 0.0
    for conf in (0.80, 0.90, 0.95, 0.99):
        iv = interval(k, n, conf=conf, method=method)
        assert iv.lower <= prev_lower + 1e-12, f"{method} conf={conf}: lower tăng khi conf tăng"
        assert iv.upper >= prev_upper - 1e-12, f"{method} conf={conf}: upper giảm khi conf tăng"
        prev_lower, prev_upper = iv.lower, iv.upper


@pytest.mark.parametrize("n", [1, 3, 10, 20, 50])
@pytest.mark.parametrize("conf", [0.90, 0.95, 0.99])
def test_property_wilson_symmetry_around_half(n, conf):
    """wilson(k,n) và wilson(n-k,n) đối xứng quanh 0.5."""
    for k in range(n + 1):
        a = interval(k, n, conf=conf, method="wilson")
        b = interval(n - k, n, conf=conf, method="wilson")
        assert a.lower == pytest.approx(1.0 - b.upper, abs=1e-12)
        assert a.upper == pytest.approx(1.0 - b.lower, abs=1e-12)


@pytest.mark.parametrize("n", [5, 10, 20])
@pytest.mark.parametrize("p", [0.05, 0.20, 0.30, 0.50, 0.72, 0.90, 0.99])
def test_property_clopper_pearson_coverage_never_below_nominal(n, p):
    """Đây là tính chất ĐỊNH NGHĨA của "exact" — và Wilson KHÔNG có nó."""
    assert coverage(n, p, 0.95, "clopper-pearson") >= 0.95 - 1e-12


def test_property_wilson_coverage_can_fall_below_nominal():
    """Mặt kia của cùng một đồng xu: đọc "Wilson95" là "khoảng 92-95%"."""
    below = [p / 100 for p in range(1, 100) if coverage(10, p / 100, 0.95, "wilson") < 0.95]
    assert below, "Wilson lẽ ra phải thủng nominal ở một số p — nếu không, coverage() sai"


@pytest.mark.parametrize("method", METHODS)
def test_property_bounds_always_inside_unit_interval(method):
    """Khác Wald: không method nào ở đây được tràn ra ngoài [0,1] hay sụp thành điểm."""
    for n in (1, 3, 10, 30):
        for k in range(n + 1):
            iv = interval(k, n, method=method)
            assert 0.0 <= iv.lower <= iv.upper <= 1.0
            assert iv.width > 0.0


@pytest.mark.parametrize("method", METHODS)
def test_property_all_pass_lower_bound_increases_with_n(method):
    prev = -1.0
    for n in range(1, 60):
        lower = interval(n, n, method=method).lower
        assert lower > prev, f"{method}: lower bound của {n}/{n} không tăng"
        prev = lower


def test_property_narrower_than_wilson_never_happens_for_wilson_cc():
    """Continuity correction luôn nới rộng, không bao giờ bóp hẹp."""
    for n in (5, 10, 30):
        for k in range(n + 1):
            w = interval(k, n, method="wilson")
            cc = interval(k, n, method="wilson-cc")
            assert cc.lower <= w.lower + 1e-12
            assert cc.upper >= w.upper - 1e-12


def test_property_scipy_wilson_cc_matches_newcombe_formula():
    """Cross-check độc lập: thư viện phải khớp công thức ở note 01 §1.4.

    Bản tự viết này sống trong test chứ không sống trong code sản phẩm — đúng
    vai trò của nó là KIỂM TRA thư viện, không phải thay thế thư viện.
    """

    def newcombe_cc(k: int, n: int, conf: float) -> tuple[float, float]:
        z = NormalDist().inv_cdf(1 - (1 - conf) / 2)
        p, z2 = k / n, z * z
        lower = (2 * n * p + z2 - 1 - z * math.sqrt(z2 - 2 - 1 / n + 4 * p * (n * (1 - p) + 1))) / (
            2 * (n + z2)
        )
        upper = (2 * n * p + z2 + 1 + z * math.sqrt(z2 + 2 - 1 / n + 4 * p * (n * (1 - p) - 1))) / (
            2 * (n + z2)
        )
        return max(0.0, lower), min(1.0, upper)

    for k, n in [(8, 10), (2, 3), (1, 20), (46, 50), (17, 20)]:
        expected = newcombe_cc(k, n, 0.95)
        got = _bounds(k, n, method="wilson-cc")
        assert got[0] == pytest.approx(expected[0], abs=1e-9)
        assert got[1] == pytest.approx(expected[1], abs=1e-9)


def test_property_wilson_center_is_not_p_hat():
    """Bài học trung tâm: center bị kéo về 0.5, nó KHÔNG bằng p̂."""
    full = interval_full(10, 10)
    assert full["p_hat"] == 1.0
    assert full["center"] == pytest.approx(0.8612, abs=1e-4)
    full100 = interval_full(100, 100)
    assert full100["center"] == pytest.approx(0.9815, abs=1e-4)


# ══════════════════════════ 3. ROUND-TRIP ══════════════════════════════════


@pytest.mark.parametrize("p", [0.0, 0.05, 0.3, 0.5, 0.72, 0.95, 1.0])
@pytest.mark.parametrize("sens", [0.6, 0.75, 0.9, 0.99])
@pytest.mark.parametrize("spec", [0.6, 0.75, 0.9, 0.99])
def test_roundtrip_rogan_gladen(p, sens, spec):
    """p -> p_obs -> p phải trả về đúng p. Nếu lệch, phép gỡ lỗi judge sai."""
    p_obs = p * sens + (1 - p) * (1 - spec)
    assert rogan_gladen(p_obs, sens, spec) == pytest.approx(p, abs=1e-9)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("target", [0.70, 0.80, 0.90, 0.95])
def test_roundtrip_min_n_all_pass_is_the_boundary(method, target):
    """N là NGƯỠNG: N đạt và N-1 không đạt. Off-by-one ở đây là sai cả bảng."""
    N = min_n_all_pass(target, method=method)
    assert interval(N, N, method=method).lower >= target
    assert interval(N - 1, N - 1, method=method).lower < target


@pytest.mark.parametrize("n", [50, 100, 200, 500])
def test_roundtrip_max_fails_is_the_boundary(n):
    f = max_fails(n, 0.90)
    assert f is not None
    assert interval(n - f, n).lower >= 0.90
    assert interval(n - f - 1, n).lower < 0.90


def test_roundtrip_prior_from_evidence_recovers_old_rate():
    """Với w=0.5, tỉ số a/(a+b) phải xấp xỉ tỉ lệ cũ."""
    a, b = prior_from_evidence(90, 100, 0.5)
    assert a / (a + b) == pytest.approx(0.90, abs=0.02)


# ══════════════════════════ EDGE CASE BẮT BUỘC ═════════════════════════════


@pytest.mark.parametrize("method", METHODS)
def test_edge_n_zero_returns_full_range_without_raising(method):
    """n=0 là ABSTAIN, không phải lỗi. Chưa đo gì thì mọi tỉ lệ còn khả dĩ."""
    iv = interval(0, 0, method=method)
    assert (iv.lower, iv.upper) == (0.0, 1.0)
    assert iv.saturated is True


@pytest.mark.parametrize("method", METHODS)
def test_edge_k_zero_lower_is_exactly_zero(method):
    assert interval(0, 30, method=method).lower == 0.0


@pytest.mark.parametrize("method", METHODS)
def test_edge_k_equals_n_upper_is_exactly_one(method):
    assert interval(30, 30, method=method).upper == 1.0


def test_edge_rule_of_three_zero_failures_is_not_zero_error_rate():
    """0/30 KHÔNG có nghĩa là lỗi bằng 0 — nó có thể tới 11.4%."""
    assert interval(0, 30).upper == pytest.approx(0.1135, abs=1e-4)
    assert interval(0, 100).upper == pytest.approx(0.0370, abs=1e-4)


def test_edge_saturated_flag_is_set_at_the_boundaries():
    assert interval(30, 30).saturated is True
    assert interval(0, 30).saturated is True
    assert interval(15, 30).saturated is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k": 11, "n": 10},
        {"k": -1, "n": 10},
        {"k": 3, "n": -1},
    ],
)
def test_edge_invalid_counts_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        interval(**kwargs)


@pytest.mark.parametrize("conf", [0.0, 1.0, -0.1, 95, 1.5])
def test_edge_conf_outside_open_unit_interval_raises(conf):
    with pytest.raises(ValueError):
        interval(3, 10, conf=conf)


@pytest.mark.parametrize("args", [(0.8, 10), (3, 10.0), (True, 10), (3, True)])
def test_edge_non_int_counts_raise_type_error(args):
    """Truyền tỉ lệ vào chỗ của số đếm là lỗi khái niệm, phải nổ chứ không ép kiểu."""
    with pytest.raises(TypeError):
        interval(*args)


def test_edge_invalid_method_raises():
    with pytest.raises(ValueError):
        interval(3, 10, method="agresti-coull")


def test_edge_mcnemar_no_discordant_pairs():
    """b=c=0 nghĩa là CHƯA ĐO ĐƯỢC, không phải "hai cái bằng nhau"."""
    out = mcnemar_wilson(0, 0)
    assert (out["lower"], out["upper"]) == (0.0, 1.0)
    assert out["conclusive"] is False
    assert out["n_disc"] == 0


def test_edge_mcnemar_conclusive_and_direction():
    out = mcnemar_wilson(20, 3)
    assert out["conclusive"] is True
    assert out["direction"] == "A"
    assert mcnemar_wilson(5, 6)["conclusive"] is False


def test_edge_posterior_prob_ge_survives_large_beta_parameters():
    """Bug có thật trong tài liệu nền: exp(logB) underflow về 0 khi a+b >= 500
    làm bản tự viết ném ZeroDivisionError. Test này là BẮT BUỘC, không tuỳ chọn."""
    for k, n in [(600, 600), (1000, 2000), (5000, 5000), (0, 900)]:
        value = posterior_prob_ge(k, n, 0.90)
        assert 0.0 <= value <= 1.0
        assert math.isfinite(value)


def test_edge_prior_weight_above_half_raises():
    """Prior nặng không phải "dùng kinh nghiệm", nó là ghi đè dữ liệu bằng niềm tin."""
    with pytest.raises(ValueError):
        prior_from_evidence(90, 100, 1.0)
    with pytest.raises(ValueError):
        prior_from_evidence(90, 100, 0.51)
    with pytest.raises(ValueError):
        prior_from_evidence(90, 100, 0.0)
    assert prior_from_evidence(90, 100, 0.5) == (45.5, 5.5)


def test_edge_diff_newcombe_requires_nonempty_samples():
    with pytest.raises(ValueError):
        diff_newcombe(0, 0, 5, 10)


def test_edge_diff_newcombe_inconclusive_is_reported_as_such():
    out = diff_newcombe(8, 10, 6, 10)
    assert out["conclusive"] is False
    assert out["direction"] is None
    assert any("không kết luận" in w for w in out["warnings"])


# ══════════════════════════ CỜ PHẢI LÊN TIẾNG ══════════════════════════════


def test_warning_is_a_readable_sentence_not_a_code():
    """Phòng thủ duy nhất chống cargo cult: công cụ phải nói thành câu."""
    full = interval_full(3, 3)
    assert full["saturated"] is True
    assert any("saturated" in w and "TRÀN" in w for w in full["warnings"])


def test_interval_returns_the_locked_contract_type():
    assert isinstance(interval(3, 10), Interval)


# ══════════════════════════════════ CLI ════════════════════════════════════


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.core.stats.intervals", *args],
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
    )


def test_cli_human_readable_prints_the_warning_line():
    proc = _run_cli("--k", "3", "--n", "3")
    assert proc.returncode == 0, proc.stderr
    assert "3/3" in proc.stdout
    assert "0.438503" in proc.stdout
    assert "WARNING" in proc.stdout


def test_cli_json_is_not_rounded():
    proc = _run_cli("--k", "8", "--n", "10", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["lower"] == interval(8, 10).lower
    assert len(repr(payload["lower"])) > len("0.490162")


def test_cli_exit_codes():
    assert main(["--k", "30", "--n", "30", "--threshold", "0.80"]) == 0
    assert main(["--k", "30", "--n", "30", "--threshold", "0.95"]) == 1
    assert main(["--k", "11", "--n", "10"]) == 2
