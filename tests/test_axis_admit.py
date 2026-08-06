"""Cổng kết nạp trục — thứ tự kiểm đóng và từng mã từ chối."""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.grid.axis_admit import (  # noqa: E402
    AdmitConfig,
    AxisCandidate,
    admit_axis,
    load_admit_config,
)

_CFG = AdmitConfig(
    allowed_tiers=("executed", "retrieved", "derived", "asserted"),
    min_reachable_values=2,
    m_cap=4,
)


def _cand(name="payment_method", members=("card", "cash"), tier="derived", ref="x.py::E"):
    return AxisCandidate(name=name, members=tuple(members), ref=ref, tier=tier)


def test_accepts_a_grounded_axis():
    r = admit_axis(_cand(), already_admitted=[], fixed_axes=[], config=_CFG)
    assert r.accepted and r.reason is None


def test_unknown_tier_rejected_before_strength():
    r = admit_axis(_cand(tier="vibes"), already_admitted=[], fixed_axes=[], config=_CFG)
    assert not r.accepted and r.reason == "unknown_tier"


def test_asserted_tier_is_never_terminal():
    r = admit_axis(_cand(tier="asserted"), already_admitted=[], fixed_axes=[], config=_CFG)
    assert not r.accepted and r.reason == "no_provenance"


def test_degenerate_single_value():
    r = admit_axis(_cand(members=("only",)), already_admitted=[], fixed_axes=[], config=_CFG)
    assert not r.accepted and r.reason == "degenerate"


def test_collinear_name_collision_dynamic():
    r = admit_axis(_cand(name="region"), already_admitted=["region"], fixed_axes=[], config=_CFG)
    assert not r.accepted and r.reason == "collinear:region"


def test_collinear_name_collision_fixed():
    r = admit_axis(_cand(name="tier"), already_admitted=[], fixed_axes=["tier"], config=_CFG)
    assert not r.accepted and r.reason == "collinear:tier"


def test_m_cap_reached():
    r = admit_axis(_cand(name="new"), already_admitted=["a", "b", "c", "d"], fixed_axes=[], config=_CFG)
    assert not r.accepted and r.reason == "m_cap_reached"


def test_order_provenance_before_degenerate():
    # tier lỗi VÀ suy biến cùng lúc → provenance thắng (kiểm trước).
    r = admit_axis(_cand(tier="vibes", members=("only",)), already_admitted=[], fixed_axes=[], config=_CFG)
    assert r.reason == "unknown_tier"


def test_load_admit_config_from_grid_yaml():
    cfg = load_admit_config()
    assert "asserted" in cfg.allowed_tiers
    assert cfg.min_reachable_values == 2
    assert cfg.m_cap == 4
