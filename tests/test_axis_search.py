"""ToT beam chọn tập trục — all-admitted, m_cap, quarantine-giữ, rejected."""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.grid.axis_admit import AdmitConfig, AxisCandidate  # noqa: E402
from app.core.grid.axis_score import SearchParams  # noqa: E402
from app.core.grid.axis_search import search_axes  # noqa: E402

_ADMIT = AdmitConfig(
    allowed_tiers=("executed", "retrieved", "derived", "asserted"),
    min_reachable_values=2,
    m_cap=4,
)


def _params(theta=0.35, m_cap=4, shallow_width=5):
    return SearchParams({
        "lambda_cost": 0.02,
        "theta_dominated": theta,
        "epsilon_marginal": 1e-6,
        "shallow_width": shallow_width,
        "deep_width": 2,
        "shallow_depth_limit": 2,
        "max_dynamic_axes": m_cap,
        "greedy_threshold_fraction": 0.75,
        "budget": {"max_wall_clock_s": 120.0, "max_nodes": 200, "max_tokens_total": 200000},
    })


def _cand(name, members=("p", "q"), tier="derived"):
    return AxisCandidate(name=name, members=tuple(members), ref=f"{name}.py::E", tier=tier)


_UNIFORM = [{"id": "all", "when": {}, "w": 1.0}]  # mọi ô w=1 → ρ=1 cho mọi trục


def test_all_admitted_when_density_uniform():
    cands = [_cand("a"), _cand("b"), _cand("c")]
    r = search_axes(cands, fixed_axes={}, rules=_UNIFORM, params=_params(), admit_config=_ADMIT)
    assert set(r.locked_axes) == {"a", "b", "c"}
    assert r.quarantined == []


def test_m_cap_caps_dynamic_axes():
    cands = [_cand(n) for n in "abcdef"]
    r = search_axes(
        cands, fixed_axes={}, rules=_UNIFORM,
        params=_params(m_cap=2), admit_config=AdmitConfig(_ADMIT.allowed_tiers, 2, 2),
    )
    assert len([n for n in r.locked_axes]) == 2


def test_dominated_axis_quarantined_not_dropped():
    # hot chỉ khi anchor=a; noise (không phải anchor) pha loãng → ρ=0.5. θ=0.6 →
    # dominated, không mở rộng được → hội tụ, noise ở quarantine chứ không biến mất.
    rules = [{"id": "hot", "when": {"anchor": "a"}, "w": 1.0}, {"id": "catch", "when": {}, "w": 0.0}]
    r = search_axes(
        [_cand("noise")], fixed_axes={"anchor": ["a", "b"]}, rules=rules,
        params=_params(theta=0.6), admit_config=_ADMIT,
    )
    assert set(r.locked_axes) == {"anchor"}  # chỉ còn trục nền
    assert [q.axis for q in r.quarantined] == ["noise"]
    assert r.quarantined[0].rho < 0.6


def test_asserted_tier_rejected_not_quarantined():
    r = search_axes(
        [_cand("weak", tier="asserted")], fixed_axes={}, rules=_UNIFORM,
        params=_params(), admit_config=_ADMIT,
    )
    assert r.locked_axes == {}
    assert ("weak", "no_provenance") in r.rejected
    assert r.quarantined == []


def test_fixed_axes_preserved_in_lock():
    r = search_axes(
        [_cand("extra")], fixed_axes={"base": ["x", "y"]}, rules=_UNIFORM,
        params=_params(), admit_config=_ADMIT,
    )
    assert "base" in r.locked_axes and r.locked_axes["base"] == ["x", "y"]
    assert "extra" in r.locked_axes  # uniform density → admitted
