"""Ghim hai con số của lưới: RWC là chỉ báo, min_per_zone là gate — và N/A bị
loại khỏi CẢ tử lẫn mẫu."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.errors import (  # noqa: E402
    ConfigError,
    ZoneWeightConflictError,
    ZoneWithoutScoreableCellsError,
)
from app.contracts.types import Band, Cell  # noqa: E402
from app.core.grid.rollup import (  # noqa: E402
    evaluate_floor,
    load_band_scores,
    load_floors,
    min_per_zone,
    risk_weighted_coverage,
)

SCORES = load_band_scores()


def cell(cid: str, zone: str, w: float, band: Band) -> Cell:
    return Cell(
        id=cid,
        axes={"payment_method": "card"},
        zone_id=zone,
        zone_w=w,
        band=band,
        source="projected",
    )


def test_band_scores_khong_co_entry_cho_NA():
    """N/A không bao giờ được chấm 0 — nó bị loại hẳn."""
    assert "N/A" not in SCORES
    assert SCORES["high"] > SCORES["med"] > SCORES["low"] >= SCORES["unknown"]


def test_rwc_tra_dict_kem_moi_mau_so_khong_bao_gio_float_tran():
    cells = [
        cell("c1", "payment_critical", 0.95, Band.HIGH),
        cell("c2", "catch_all", 0.2, Band.LOW),
    ]
    out = risk_weighted_coverage(cells, SCORES)
    assert set(out) == {"value", "cells_total", "cells_scored", "cells_excluded_na"}
    assert out["cells_total"] == 2
    assert out["cells_scored"] == 2
    assert out["cells_excluded_na"] == 0
    assert out["value"] == pytest.approx((0.95 * 1.0 + 0.2 * 0.2) / (0.95 + 0.2))


def test_rwc_value_la_None_khi_khong_con_gi_cham_duoc():
    """Báo 0.0 ở đây là trình bày "không có dữ liệu" thành "đã đo và bằng không"."""
    cells = [cell("c1", "payment_critical", 0.95, Band.NA)]
    out = risk_weighted_coverage(cells, SCORES)
    assert out["value"] is None
    assert out["cells_scored"] == 0
    assert out["cells_excluded_na"] == 1


def test_NA_bi_loai_khoi_CA_tu_lan_mau():
    khong_NA = [cell("c1", "payment_critical", 0.95, Band.HIGH)]
    co_NA = khong_NA + [cell("c2", "catch_all", 0.2, Band.NA)]
    assert (
        risk_weighted_coverage(co_NA, SCORES)["value"]
        == risk_weighted_coverage(khong_NA, SCORES)["value"]
    )
    assert risk_weighted_coverage(co_NA, SCORES)["cells_excluded_na"] == 1


def test_NA_khac_han_unknown():
    """Nếu N/A bị chấm như unknown (0.0) thì hai lượt này sẽ ra cùng con số."""
    nhu_NA = [
        cell("c1", "payment_critical", 0.95, Band.HIGH),
        cell("c2", "catch_all", 0.2, Band.NA),
    ]
    nhu_unknown = [
        cell("c1", "payment_critical", 0.95, Band.HIGH),
        cell("c2", "catch_all", 0.2, Band.UNKNOWN),
    ]
    assert (
        risk_weighted_coverage(nhu_NA, SCORES)["value"]
        != risk_weighted_coverage(nhu_unknown, SCORES)["value"]
    )


def test_min_per_zone_luon_tra_cau_truc_per_zone_khong_bao_gio_scalar():
    cells = [
        cell("c1", "payment_critical", 0.95, Band.HIGH),
        cell("c2", "payment_critical", 0.95, Band.LOW),
        cell("c3", "catch_all", 0.2, Band.HIGH),
    ]
    out = min_per_zone(cells, SCORES)
    assert isinstance(out, dict)
    assert set(out) == {"payment_critical", "catch_all"}
    assert not isinstance(out, (int, float))
    assert out["payment_critical"]["worst_band"] == "low"
    assert out["payment_critical"]["worst_score"] == SCORES["low"]
    assert out["payment_critical"]["worst_cell_id"] == "c2"
    assert out["catch_all"]["worst_band"] == "high"


def test_mot_zone_cao_khong_che_duoc_mot_zone_thap_o_cho_khac():
    """Đây là toàn bộ lý do gate đọc per-zone chứ không đọc trung bình."""
    cells = [
        cell(f"h{i}", "catch_all", 0.2, Band.HIGH) for i in range(20)
    ] + [cell("x", "payment_critical", 0.95, Band.UNKNOWN)]
    out = min_per_zone(cells, SCORES)
    assert out["payment_critical"]["worst_score"] == SCORES["unknown"]
    assert out["catch_all"]["worst_score"] == SCORES["high"]


def test_zone_mat_het_o_cham_duoc_thi_raise_chu_khong_bien_mat():
    cells = [
        cell("c1", "payment_critical", 0.95, Band.NA),
        cell("c2", "catch_all", 0.2, Band.HIGH),
    ]
    with pytest.raises(ZoneWithoutScoreableCellsError):
        min_per_zone(cells, SCORES)


def test_hai_o_cung_zone_khai_w_khac_nhau_thi_raise():
    """Không average, không max, không first-wins."""
    cells = [
        cell("c1", "payment_critical", 0.95, Band.HIGH),
        cell("c2", "payment_critical", 0.10, Band.HIGH),
    ]
    with pytest.raises(ZoneWeightConflictError):
        min_per_zone(cells, SCORES)
    with pytest.raises(ZoneWeightConflictError):
        risk_weighted_coverage(cells, SCORES)


def test_band_khong_co_diem_trong_config_thi_neu_dich_danh():
    cells = [cell("c1", "catch_all", 0.2, Band.HIGH)]
    thieu = {k: v for k, v in SCORES.items() if k != "high"}
    with pytest.raises(ConfigError) as excinfo:
        risk_weighted_coverage(cells, thieu)
    assert "high" in excinfo.value.key


def test_luoi_rong_khong_gia_vo_da_do_duoc_gi():
    out = risk_weighted_coverage([], SCORES)
    assert out["value"] is None
    assert out["cells_total"] == 0
    assert min_per_zone([], SCORES) == {}


# ─────────────────────────── sàn theo zone ───────────────────────────


def test_floor_yaml_that_doc_duoc_va_moi_muc_co_ly_do():
    floors = load_floors()
    assert floors.default_min_score > 0
    for zone_id, entry in floors.zones.items():
        assert entry["reason"].strip(), f"zone {zone_id} thiếu lý do"


def test_evaluate_floor_van_la_per_zone():
    cells = [
        cell("c1", "payment_critical", 0.95, Band.MED),
        cell("c2", "catch_all", 0.2, Band.LOW),
    ]
    verdicts = evaluate_floor(min_per_zone(cells, SCORES), load_floors())
    assert verdicts["payment_critical"]["meets_floor"] is False
    assert verdicts["catch_all"]["meets_floor"] is True
    assert verdicts["payment_critical"]["reason"]


def test_san_ghi_de_thieu_reason_thi_dung_lai(tmp_path):
    (tmp_path / "floor.yaml").write_text(
        "default_min_score: 0.6\nzones:\n  payment_critical:\n    min_score: 1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as excinfo:
        load_floors(config_dir=tmp_path)
    assert excinfo.value.key == "zones.payment_critical.reason"


def test_thieu_default_min_score_thi_neu_dich_danh_ten_khoa(tmp_path):
    (tmp_path / "floor.yaml").write_text("zones: {}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        load_floors(config_dir=tmp_path)
    assert excinfo.value.key == "default_min_score"
