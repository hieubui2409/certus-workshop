"""Ghim ba luật của zone: first-match-wins, trục vắng không raise, tập chặn
không được rỗng."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.errors import ConfigError, EmptyBlockingSetError  # noqa: E402
from app.core.grid.zones import (  # noqa: E402
    compile_zones,
    is_blocking,
    is_hot,
    load_zone_config,
    match_zone,
    require_zone,
)

RULES = [
    {"id": "payment_critical", "when": {"payment_method": ["card", "wallet"]}, "w": 0.95},
    {"id": "checkout_core", "when": {"cart_state": ["checkout", "paid"]}, "w": 0.75},
    {"id": "catch_all", "when": {}, "w": 0.2},
]


def test_first_match_wins_theo_dung_thu_tu_khai_bao():
    cell = {"payment_method": "card", "cart_state": "checkout"}
    assert match_zone(cell, RULES)["id"] == "payment_critical"


def test_dao_hai_rule_that_su_doi_zone_cua_o():
    """Thứ tự rule là load-bearing: đây là bằng chứng, không phải lời hứa."""
    cell = {"payment_method": "card", "cart_state": "checkout"}
    dao = [RULES[1], RULES[0], RULES[2]]
    assert match_zone(cell, RULES)["id"] == "payment_critical"
    assert match_zone(cell, dao)["id"] == "checkout_core"
    assert match_zone(cell, RULES)["w"] != match_zone(cell, dao)["w"]


def test_truc_co_trong_when_ma_vang_trong_o_thi_khong_khop_va_KHONG_raise():
    """Ô t=2 chỉ mang 2 trục, còn rule có quyền nói về trục thứ ba."""
    cell = {"user_tier": "plus", "currency": "vnd"}
    zone = match_zone(cell, RULES)
    assert zone["id"] == "catch_all"


def test_gia_tri_don_le_trong_when_cung_khop_duoc():
    rules = [{"id": "chi_cod", "when": {"payment_method": "cod"}, "w": 0.9}]
    assert match_zone({"payment_method": "cod"}, rules)["id"] == "chi_cod"
    assert match_zone({"payment_method": "card"}, rules) is None


def test_khong_rule_nao_khop_thi_tra_None():
    rules = [{"id": "hep", "when": {"payment_method": "cod"}, "w": 0.9}]
    assert match_zone({"user_tier": "free"}, rules) is None


def test_require_zone_dung_lai_khi_bang_zone_khong_toan_phan():
    rules = [{"id": "hep", "when": {"payment_method": "cod"}, "w": 0.9}]
    with pytest.raises(ConfigError):
        require_zone({"user_tier": "free"}, rules)


def test_compile_zones_raise_khi_tap_chan_rong():
    """B18 — bên bị chấm không được làm rỗng tập chặn."""
    ha_het = [dict(r, w=0.1) for r in RULES]
    with pytest.raises(EmptyBlockingSetError):
        compile_zones(ha_het, blocking_w=0.7)


def test_compile_zones_chap_nhan_khi_con_it_nhat_mot_zone_chan():
    compiled = compile_zones(RULES, blocking_w=0.7)
    assert [z["id"] for z in compiled] == [r["id"] for r in RULES]
    assert any(z["w"] >= 0.7 for z in compiled)


def test_compile_zones_tu_choi_zone_id_trung():
    trung = RULES + [{"id": "catch_all", "when": {}, "w": 0.9}]
    with pytest.raises(ConfigError):
        compile_zones(trung, blocking_w=0.7)


def test_compile_zones_neu_dich_danh_khoa_thieu():
    with pytest.raises(ConfigError) as excinfo:
        compile_zones([{"id": "x", "when": {}}], blocking_w=0.7)
    assert excinfo.value.key == "rules[0].w"


def test_is_blocking_va_is_hot_khong_nhan_None_lam_ket_luan_tot():
    assert is_blocking(None, blocking_w=0.7) is False
    assert is_hot(None, hot_w=0.85) is False
    assert is_blocking(RULES[0], blocking_w=0.7) is True
    assert is_hot(RULES[0], hot_w=0.85) is True
    assert is_hot(RULES[1], hot_w=0.85) is False


def test_zones_yaml_that_compile_duoc_va_tap_chan_khac_rong():
    cfg = load_zone_config()
    assert cfg.hot_w >= cfg.blocking_w
    assert any(z["w"] >= cfg.blocking_w for z in cfg.rules)
    assert cfg.rules[-1]["when"] == {}, "rule catch-all phải nằm cuối"
