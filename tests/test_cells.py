"""Ghim mẫu số: id ô, công thức đóng, và giới hạn ĐÃ ĐO của allpairspy.

Mỗi test ở đây trả lời một câu duy nhất: "cách này có làm mẫu số co lại trong
im lặng không?"
"""

from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.errors import ConfigError  # noqa: E402
from app.core.grid.cells import (  # noqa: E402
    cell_axes,
    cell_id,
    count_cartesian,
    count_t_wise,
    enumerate_t_wise,
    load_grid_config,
    require_key,
    t_wise_degree,
)

AXES = {
    "payment_method": ["card", "wallet", "cod"],
    "cart_state": ["empty", "browsing", "checkout", "paid"],
    "user_tier": ["free", "plus"],
    "currency": ["vnd", "usd", "jpy", "eur"],
}


def test_cell_id_la_canonical_va_theo_thu_tu_axis_lock():
    cell = (("payment_method", "cart_state"), ("card", "checkout"))
    assert cell_id(cell) == "cell:payment_method=card|cart_state=checkout"
    assert cell_id(cell, list(AXES)) == "cell:payment_method=card|cart_state=checkout"


def test_cell_id_tu_choi_thu_tu_lech_axis_lock():
    """Cùng một ô mang hai tên là hai hàng khác nhau trong sổ — nên lệch thứ tự
    phải nổ, không được tự sắp lại rồi đi tiếp."""
    lech = (("cart_state", "payment_method"), ("checkout", "card"))
    with pytest.raises(ValueError):
        cell_id(lech, list(AXES))


def test_cell_id_tu_choi_truc_khong_co_trong_lock():
    with pytest.raises(ValueError):
        cell_id((("khong_ton_tai",), ("x",)), list(AXES))


def test_cell_axes_giu_dung_cap_ten_gia_tri():
    cell = (("user_tier", "currency"), ("plus", "jpy"))
    assert cell_axes(cell) == {"user_tier": "plus", "currency": "jpy"}


def test_count_cartesian_tich_rong_bang_mot():
    assert count_cartesian({}) == 1
    assert count_cartesian(AXES) == 3 * 4 * 2 * 4


@pytest.mark.parametrize("t", [1, 2, 3, 4])
def test_cong_thuc_dong_khop_enumeration_that(t):
    """Công thức đóng và enumeration phải cho CÙNG một con số. Đây là chỗ duy
    nhất phát hiện được một generator thiếu ô."""
    assert count_t_wise(AXES, t) == sum(1 for _ in enumerate_t_wise(AXES, t))


def test_cong_thuc_t2_rut_ve_S_binh_phuong_tru_tong_binh_phuong():
    sizes = [len(v) for v in AXES.values()]
    S = sum(sizes)
    expected = (S**2 - sum(a * a for a in sizes)) // 2
    assert count_t_wise(AXES, 2) == expected


def test_t_ngoai_khoang_tra_ve_rong_khong_phai_loi():
    assert count_t_wise(AXES, 0) == 0
    assert count_t_wise(AXES, 5) == 0
    assert list(enumerate_t_wise(AXES, 0)) == []
    assert list(enumerate_t_wise(AXES, 5)) == []


def test_exclude_dem_bang_enumeration_that_khong_xap_xi():
    """Có `exclude` thì công thức đóng không còn đúng — hàm phải đếm thật."""

    def impossible(cell):
        axes = cell_axes(cell)
        return axes.get("cart_state") == "empty" and axes.get("payment_method") == "card"

    counted = count_t_wise(AXES, 2, exclude=impossible)
    enumerated = sum(1 for _ in enumerate_t_wise(AXES, 2, exclude=impossible))
    assert counted == enumerated
    assert counted == count_t_wise(AXES, 2) - 1


def test_o_bat_kha_thi_that_su_bien_mat_khoi_luoi():
    """Bất khả thi khác chưa ghé: ô bị exclude không được còn nằm trong mẫu số."""

    def impossible(cell):
        return cell_axes(cell).get("currency") == "jpy"

    ids = {cell_id(c) for c in enumerate_t_wise(AXES, 2, exclude=impossible)}
    assert not any("currency=jpy" in i for i in ids)


def test_t2_phu_du_tich_descartes_cua_tung_cap_truc():
    """t=2 đi qua allpairspy — nó phải phủ ĐỦ tích Descartes của từng cặp trục,
    không phải một covering array rút gọn."""
    for a, b in itertools.combinations(AXES, 2):
        pairs = {
            cell[1]
            for cell in enumerate_t_wise(AXES, 2)
            if cell[0] == (a, b)
        }
        assert pairs == set(itertools.product(AXES[a], AXES[b]))


def test_t3_khong_bi_rut_gon_boi_covering_array():
    """Giới hạn ĐÃ ĐO của allpairspy 2.5.1: với 3 tham số và n=3 nó trả 14 hàng
    trong khi số ô thật là 24. Test này ghim rằng bậc >= 3 KHÔNG đi qua nó."""
    three = {k: AXES[k] for k in ("payment_method", "user_tier", "currency")}
    cells = [c for c in enumerate_t_wise(three, 3)]
    assert len(cells) == math.prod(len(v) for v in three.values()) == 24
    assert {c[1] for c in cells} == set(itertools.product(*three.values()))


def test_thu_tu_lap_bam_theo_thu_tu_chen_cua_axes():
    first = next(enumerate_t_wise(AXES, 2))
    assert first[0] == ("payment_method", "cart_state")


def test_require_key_neu_dich_danh_ten_khoa():
    with pytest.raises(ConfigError) as excinfo:
        require_key({"search": {}}, "search.lambda_cost", source="grid.yaml")
    assert excinfo.value.key == "search.lambda_cost"


def test_grid_yaml_giu_hai_bac_rieng_biet():
    cfg = load_grid_config()
    assert require_key(cfg, "t_wise_degree", source="grid.yaml") == t_wise_degree()
    assert require_key(cfg, "escalation_degree", source="grid.yaml") != require_key(
        cfg, "t_wise_degree", source="grid.yaml"
    )
