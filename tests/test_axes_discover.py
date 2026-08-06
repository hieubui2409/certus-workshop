"""Endpoint khám phá trục — verdict engine cho từng trục (gọi thẳng hàm route)."""

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.api.routes.axes import AxisDiscoveryRequest, axes_discover  # noqa: E402


def _discover(**kw):
    return asyncio.run(axes_discover(AxisDiscoveryRequest(**kw), principal=None))


def test_shopcart_engine_tot_all_locked():
    r = _discover(target="shopcart")
    assert r.engine == "tot"
    assert {c.axis for c in r.candidates} == {
        "customer_tier", "shipping_zone", "payment_method", "coupon_type"
    }
    assert all(c.kept and c.verdict == "locked" for c in r.candidates)
    # ρ hiển thị (leave-one-out) của trục locked phải NHẤT QUÁN verdict: ≥ θ.
    for c in r.candidates:
        assert c.rho is not None and c.rho >= 0.35


def test_ledger_engine_floor_keeps_all():
    r = _discover(target="ledger")
    assert r.engine == "floor"
    assert all(c.kept and c.verdict == "floored" for c in r.candidates)


def test_candidates_carry_source_and_members():
    r = _discover(target="shopcart")
    c = next(c for c in r.candidates if c.axis == "payment_method")
    assert len(c.members) >= 2
    assert "::" in c.source  # neo file::Enum


def test_sample_is_read_only_with_academic_note():
    # Repo mẫu: panel KHÓA (read_only) + note học thuật, tập trục cố định.
    r = _discover(target="shopcart")
    assert r.read_only is True
    assert "Repo mẫu" in (r.note or "")


def test_sample_candidates_are_enum_only():
    # Repo mẫu KHÔNG bật đa nguồn — mọi trục là enum/retrieved (giữ cassette bất biến).
    r = _discover(target="shopcart")
    assert all(c.origin == "enum" and c.tier == "retrieved" for c in r.candidates)
