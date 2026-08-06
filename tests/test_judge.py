"""Test cho `app.core.stats.judge`.

Câu hỏi mà mọi test ở đây phục vụ: "ai chấm điểm, và cái thước đó đã được đo
chưa?". Ba dạng sai bị đóng đinh riêng từng cái:

  * thước chưa từng bị kiểm (mẫu số rỗng)  -> phải rejected, không phải ok
  * thước quá yếu (J < 0.5)                -> phải TỪ CHỐI, không phải hiệu chỉnh
  * interval tràn rồi bị cắt               -> phải lộ ra là tràn, không phải hẹp

Neo: docs/research-notes/01-confidence-intervals.md §1.6, §4.4, §5.C
     docs/design/sdd/01-core-stats.md §5
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.stats.judge import judge_adjust, judge_screen, rogan_gladen  # noqa: E402


# ═════════════════════════════ judge_screen ════════════════════════════════


def test_screen_matches_e23_anchor():
    """Dữ liệu THẬT từ E23. J=0.4650 -> 1/J=2.15 -> thước này bị loại."""
    out = judge_screen(TP=9, FN=4, TN=17, FP=5)
    assert out["sens"] == pytest.approx(9 / 13, abs=1e-9)
    assert out["spec"] == pytest.approx(17 / 22, abs=1e-9)
    assert out["youden_j"] == pytest.approx(0.4650, abs=1e-4)
    assert out["error_amplification"] == pytest.approx(2.150, abs=1e-3)
    assert out["verdict"] == "rejected"


def test_screen_rejects_when_no_positive_cases_were_ever_scored():
    """TP+FN=0: sensitivity chưa từng được đo. Không đo được KHÔNG phải là đạt."""
    out = judge_screen(TP=0, FN=0, TN=50, FP=0)
    assert out["verdict"] == "rejected"
    assert out["sens"] is None
    assert any("POSITIVE" in w for w in out["warnings"])


def test_screen_rejects_when_no_negative_cases_were_ever_scored():
    """Bộ mẫu không có ca âm là ca đã đo được: chương trình chỉ in `0` vẫn "đúng"."""
    out = judge_screen(TP=50, FN=0, TN=0, FP=0)
    assert out["verdict"] == "rejected"
    assert out["spec"] is None


def test_screen_flags_bias_toward_passing():
    """Câu cảnh báo phải nói HƯỚNG lệch, vì hai hướng có hậu quả khác nhau."""
    out = judge_screen(TP=95, FN=5, TN=60, FP=40)
    assert out["verdict"] == "biased"
    assert any("biased toward passing" in w for w in out["warnings"])


def test_screen_flags_bias_toward_failing():
    out = judge_screen(TP=60, FN=40, TN=95, FP=5)
    assert out["verdict"] == "biased"
    assert any("biased toward failing" in w for w in out["warnings"])


def test_screen_accepts_a_balanced_strong_judge():
    out = judge_screen(TP=90, FN=10, TN=88, FP=12)
    assert out["verdict"] == "ok"
    assert out["tier"] == 2


def test_screen_rejection_takes_priority_over_bias():
    """Thước vừa yếu vừa lệch thì điều cần nói là nó YẾU."""
    out = judge_screen(TP=90, FN=10, TN=30, FP=70)
    assert out["youden_j"] < 0.5
    assert out["verdict"] == "rejected"


@pytest.mark.parametrize("n_calib,tier", [(20, 0), (50, 1), (199, 1), (200, 2), (400, 2)])
def test_screen_calibration_tiers(n_calib, tier):
    half = n_calib // 2
    out = judge_screen(TP=half, FN=0, TN=n_calib - half, FP=0)
    assert out["tier"] == tier


def test_screen_small_calibration_set_says_stop():
    out = judge_screen(TP=9, FN=1, TN=9, FP=1)
    assert out["tier"] == 0
    assert any("uncalibrated" in w for w in out["warnings"])


def test_screen_says_judge_error_is_still_uncorrected_even_when_ok():
    """Judge qua cổng KHÔNG có nghĩa lỗi của nó đã được gỡ khỏi con số cuối."""
    out = judge_screen(TP=90, FN=10, TN=88, FP=12)
    assert any("CHƯA được hiệu chỉnh" in w for w in out["warnings"])


def test_screen_rejects_negative_counts():
    with pytest.raises(ValueError):
        judge_screen(TP=-1, FN=0, TN=10, FP=10)
    with pytest.raises(TypeError):
        judge_screen(TP=0.5, FN=0, TN=10, FP=10)


# ═════════════════════════════ rogan_gladen ════════════════════════════════


@pytest.mark.parametrize("p", [0.0, 0.1, 0.5, 0.83, 1.0])
@pytest.mark.parametrize("sens,spec", [(0.7, 0.9), (0.95, 0.95), (0.6, 0.85), (0.99, 0.6)])
def test_rogan_gladen_roundtrip(p, sens, spec):
    p_obs = p * sens + (1 - p) * (1 - spec)
    assert rogan_gladen(p_obs, sens, spec) == pytest.approx(p, abs=1e-9)


def test_rogan_gladen_returns_none_when_judge_is_no_better_than_a_coin():
    """sens+spec <= 1: phép đảo không tồn tại. Trả số ở đây sẽ là bịa."""
    assert rogan_gladen(0.9, 0.5, 0.5) is None
    assert rogan_gladen(0.9, 0.3, 0.4) is None


def test_rogan_gladen_does_not_clamp():
    """1.0259 là TÍN HIỆU BÁO ĐỘNG, không phải con số để cắt gọn."""
    value = rogan_gladen(0.95, 0.9, 0.9)
    assert value is not None and value > 1.0
    low = rogan_gladen(0.02, 0.9, 0.9)
    assert low is not None and low < 0.0


def test_rogan_gladen_rejects_out_of_range_inputs():
    with pytest.raises(ValueError):
        rogan_gladen(1.2, 0.9, 0.9)
    with pytest.raises(ValueError):
        rogan_gladen(0.5, 1.5, 0.9)


# ═════════════════════════════ judge_adjust ════════════════════════════════


def test_adjust_refuses_and_returns_full_range_for_a_weak_judge():
    """E23: J=0.4650 -> interval hợp nhất [0,1], vô thông tin. KHÔNG chia 0."""
    out = judge_adjust(46, 50, TP=9, FN=4, TN=17, FP=5)
    assert out["verdict"] == "rejected"
    assert (out["lower"], out["upper"]) == (0.0, 1.0)
    assert out["raw_lower"] is None and out["raw_upper"] is None
    assert out["saturated_low"] is True and out["saturated_high"] is True
    assert any("vô thông tin" in w for w in out["warnings"])


def test_adjust_does_not_divide_by_zero_when_youden_j_is_exactly_zero():
    out = judge_adjust(46, 50, TP=50, FN=50, TN=50, FP=50)
    assert out["youden_j"] == pytest.approx(0.0, abs=1e-12)
    assert (out["lower"], out["upper"]) == (0.0, 1.0)
    assert out["verdict"] == "rejected"


def test_adjust_handles_empty_calibration_without_raising():
    out = judge_adjust(46, 50, TP=0, FN=0, TN=0, FP=0)
    assert out["verdict"] == "rejected"
    assert (out["lower"], out["upper"]) == (0.0, 1.0)


def test_adjust_returns_raw_bounds_alongside_clamped_ones():
    """Bẫy thị giác C4: sau clamp thì thước tệ trông chắc chắn nhất.

    Không có raw_* thì không cách nào phân biệt "hẹp vì nhiều dữ liệu" với
    "hẹp vì đã tràn rồi bị cắt".
    """
    out = judge_adjust(46, 50, TP=80, FN=20, TN=80, FP=20)
    assert out["verdict"] in ("ok", "biased")
    assert out["raw_upper"] is not None and out["raw_upper"] > 1.0
    assert out["upper"] == 1.0
    assert out["saturated_high"] is True
    assert out["raw_width"] > out["width"]
    assert any("TRÀN" in w for w in out["warnings"])


def test_adjust_point_estimate_outside_unit_interval_is_reported_not_hidden():
    out = judge_adjust(46, 50, TP=80, FN=20, TN=80, FP=20)
    assert out["point_raw"] == pytest.approx(1.2, abs=1e-9)
    assert any("NGOÀI [0,1]" in w for w in out["warnings"])


def test_adjust_bonferroni_split_widens_each_component():
    """Ba nguồn bất định thì mỗi cái phải gánh alpha/3, không phải alpha."""
    out = judge_adjust(46, 50, TP=190, FN=10, TN=185, FP=15, conf=0.95, split=3)
    assert out["conf_each"] == pytest.approx(1 - 0.05 / 3, abs=1e-12)
    narrow = judge_adjust(46, 50, TP=190, FN=10, TN=185, FP=15, conf=0.95, split=1)
    assert (out["upper"] - out["lower"]) >= (narrow["upper"] - narrow["lower"]) - 1e-12


def test_adjust_good_judge_gives_a_usable_interval():
    out = judge_adjust(40, 50, TP=196, FN=4, TN=196, FP=4)
    assert out["verdict"] == "ok"
    assert 0.0 < out["lower"] < out["upper"] < 1.0
    assert out["raw_lower"] == pytest.approx(out["lower"], abs=1e-12)
    assert out["raw_upper"] == pytest.approx(out["upper"], abs=1e-12)
    assert out["saturated"] is False


def test_adjust_even_a_strong_judge_saturates_at_a_high_pass_rate():
    """Đo được: judge 0.95/0.925 trên 40/50 vẫn cho raw_upper > 1.

    Bài học là saturation KHÔNG phải dấu hiệu "thước tệ" — nó là dấu hiệu
    "mô hình hiệu chỉnh đã hết chỗ", và nó xuất hiện sớm hơn người ta tưởng.
    """
    out = judge_adjust(40, 50, TP=190, FN=10, TN=185, FP=15)
    assert out["verdict"] == "ok"
    assert out["raw_upper"] > 1.0
    assert out["upper"] == 1.0
    assert out["saturated_high"] is True


def test_adjust_correction_is_wider_than_the_uncorrected_observation():
    """Gỡ lỗi judge KHÔNG bao giờ làm con số chắc hơn — nó cộng thêm bất định."""
    out = judge_adjust(40, 50, TP=190, FN=10, TN=185, FP=15)
    obs_lower, obs_upper = out["obs_interval"]
    assert (out["upper"] - out["lower"]) > (obs_upper - obs_lower)


def test_adjust_weaker_judge_gives_a_wider_raw_interval():
    """Thước càng tệ, khoảng THÔ càng nở — dù khoảng sau clamp có thể trông hẹp."""
    strong = judge_adjust(40, 50, TP=196, FN=4, TN=196, FP=4)
    weak = judge_adjust(40, 50, TP=160, FN=40, TN=160, FP=40)
    assert weak["raw_width"] > strong["raw_width"]


def test_adjust_rejects_bad_split():
    with pytest.raises(ValueError):
        judge_adjust(40, 50, TP=190, FN=10, TN=185, FP=15, split=0)


def test_adjust_all_returned_numbers_are_finite_or_none():
    """JSON không biểu diễn được Infinity; vô cực phải thành None chứ không phải inf."""
    for out in (
        judge_adjust(46, 50, TP=9, FN=4, TN=17, FP=5),
        judge_adjust(46, 50, TP=80, FN=20, TN=80, FP=20),
        judge_adjust(40, 50, TP=190, FN=10, TN=185, FP=15),
    ):
        for key, value in out.items():
            if isinstance(value, float):
                assert math.isfinite(value), f"{key} = {value}"
