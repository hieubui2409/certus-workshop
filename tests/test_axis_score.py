"""Chấm điểm chọn trục — ρ, cost, và bài Goodhart naive-vs-ρ.

Khoá HAI hành vi: (1) ρ = mật độ trung bình khi zone không phân biệt trục mới
(nên trục thêm vào không bị coi dominated một cách vô cớ); (2) ρ TỤT dưới θ khi
trục mới đẩy tổ hợp vào một catch-all trọng số thấp — và đúng lúc đó naive_score
VẪN không coi là dominated (bug Goodhart).
"""

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.grid import axis_score as S  # noqa: E402


# Zone tổng hợp: payment=card là high (w=1), còn lại rơi catch-all w=0.
_RULES = [
    {"id": "hot", "when": {"payment_method": "card"}, "w": 1.0},
    {"id": "catch_all", "when": {}, "w": 0.0},
]


def test_count_cartesian_empty_is_one():
    assert S.count_cartesian({}) == 1
    assert S.count_cartesian({"a": ["x", "y"], "b": ["p", "q", "r"]}) == 6


def test_value_sums_matched_zone_weights():
    axes = {"payment_method": ["card", "cash", "transfer"]}
    # card→1.0, cash→0, transfer→0
    assert S.value(axes, _RULES) == pytest.approx(1.0)


def test_marginal_density_uniform_when_zone_ignores_new_axis():
    # Thêm một trục mà zone KHÔNG nhắc tới: mỗi ô mới thừa kế đúng phân bố zone,
    # nên ρ = mật độ trung bình hiện tại, KHÔNG tụt — trục không bị dominated vô cớ.
    a = {"payment_method": ["card", "cash"]}  # V=1.0, cells=2 → avg 0.5
    rho = S.marginal_risk_density(a, "region", ["vn", "us"], _RULES, epsilon=1e-9)
    assert rho == pytest.approx(0.5)


def test_marginal_density_drops_when_new_axis_dilutes_into_catchall():
    # Trục nhiễu cardinality cao: card vẫn high nhưng bị pha loãng — ρ vẫn = avg
    # vì zone chỉ xét payment_method. Để domination BẮN, cần zone phụ thuộc trục
    # cũ theo cách mà trục mới KHÔNG khớp: dùng zone yêu cầu region=vn.
    rules = [
        {"id": "hot", "when": {"payment_method": "card", "region": "vn"}, "w": 1.0},
        {"id": "catch_all", "when": {}, "w": 0.0},
    ]
    a = {"payment_method": ["card"], "region": ["vn"]}  # 1 ô, khớp hot → V=1, avg=1.0
    # thêm trục 8 giá trị: 8 ô, chỉ (card,vn,*) khớp hot=1, 7 ô còn lại catch_all=0
    rho = S.marginal_risk_density(a, "noise", list("abcdefgh"), rules, epsilon=1e-9)
    # ΔV = 8*? ... V(a∪x): card,vn cố định, 8 ô đều (card,vn) → tất cả khớp hot!
    # nên đây KHÔNG dilute. Kiểm ca dilute thật: nới a để noise tạo tổ hợp ngoài hot.
    assert rho == pytest.approx(1.0)  # mọi ô vẫn (card,vn) → không loãng

    # Ca dilute thật: base có payment {card, cash}; hot chỉ card. Thêm noise 4 giá trị.
    a2 = {"payment_method": ["card", "cash"]}  # V=1 (chỉ card), cells=2, avg .5
    rho2 = S.marginal_risk_density(a2, "noise", list("abcd"), rules, epsilon=1e-9)
    # cells: 2→8 (Δ6). V: chỉ ô có payment=card&region=vn khớp — nhưng a2 không có
    # region, nên hot (đòi region) không khớp ô nào → V(a2)=0, V(a2∪noise)=0 → ρ=0.
    assert rho2 == pytest.approx(0.0)
    assert S.is_dominated(rho2, theta=0.35) is True


def test_goodhart_naive_misses_what_rho_catches():
    # Trục dominated theo ρ (ρ=0 < θ) mà naive_score KHÔNG coi là dominated:
    # V không đổi (0), cost tăng chút → naive_score GIẢM? Không: V=0 cả hai, cost
    # tăng → naive giảm → naive True ở ca này. Chọn ca V dương để lộ Goodhart.
    rules = [{"id": "hot", "when": {"payment_method": "card"}, "w": 1.0},
             {"id": "catch", "when": {}, "w": 0.0}]
    a = {"payment_method": ["card", "cash", "transfer"]}  # V=1, cells=3
    # thêm trục nhiễu 5 giá trị: V→5 (5 ô card khớp hot), cells→15, ρ=(5-1)/(15-3)=0.333
    rho = S.marginal_risk_density(a, "noise", list("abcde"), rules, epsilon=1e-9)
    assert rho == pytest.approx(4 / 12)
    assert S.is_dominated(rho, theta=0.35) is True  # ρ=0.333 < 0.35 → dominated
    # naive: V tăng 1→5, cost tăng 0.02*(15-3)=0.24 → naive tăng 4-0.24>0 → KHÔNG dominated
    assert S.naive_is_dominated(a, "noise", list("abcde"), rules, lam=0.02) is False


def test_degenerate_marginal_raises_on_single_value_axis():
    a = {"payment_method": ["card", "cash"]}
    with pytest.raises(S.DegenerateMarginalError):
        # trục 1 giá trị: cells 2→2, Δ=0 < ε
        S.marginal_risk_density(a, "unit", ["only"], _RULES, epsilon=1e-6)


def test_search_params_load_from_config():
    p = S.load_search_params()
    assert p.lam == 0.02
    assert p.theta == 0.35
    assert p.m_cap == 4
