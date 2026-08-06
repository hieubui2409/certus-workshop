"""Ghim bảng band projection: từng nhánh, thứ tự nhánh, và hai luật cứng —
N/A thắng trước, stub chỉ che hàng DEFAULT."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.errors import NAConflictError  # noqa: E402
from app.contracts.types import Band  # noqa: E402
from app.core.grid.project import load_projection_params, project_cell  # noqa: E402

BLOCKING_W = 0.7
ZONE_BLOCKING = {"id": "payment_critical", "when": {}, "w": 0.95}
ZONE_COLD = {"id": "catch_all", "when": {}, "w": 0.2}
CELL_ID = "cell:payment_method=card|cart_state=checkout"
AXES = {"payment_method": "card", "cart_state": "checkout"}

PARAMS = load_projection_params()

BINDING = {
    "probe_sha256": "sha-p",
    "seed_id": "seed-1",
    "cell_id": CELL_ID,
    "operator": "CompareOpSwap",
    "target_path": "src/cart.py",
}


def obs(**overrides):
    base = {
        "outcome": "resolved",
        "test_exit_code": 0,
        "probe_sha256": "sha-p",
        "artifact_probe_sha256": "sha-p",
        "cov_cell": {"src/cart.py:42"},
        "cov_suite": {"src/cart.py:42", "src/cart.py:43"},
        "code_path": "src/cart.py:42",
        "assert_count": 2,
        "calibration_seed_id": "seed-1",
        "mutation_run": {
            "verdict": "killed",
            "seed_id": "seed-1",
            "binding": dict(BINDING),
        },
        "evidence_id": ["ev-1"],
    }
    base.update(overrides)
    return base


def project(zone=ZONE_BLOCKING, **kwargs):
    return project_cell(
        cell_id=CELL_ID,
        axes=AXES,
        zone=zone,
        blocking_w=BLOCKING_W,
        params=PARAMS,
        **kwargs,
    )


# ─────────────────────────── N/A thắng trước ───────────────────────────


def test_constraint_da_admit_cho_ra_NA_va_thang_truoc_moi_quan_sat():
    cell = project(constraint={"id": "impossible_pair"}, observation=obs(test_exit_code=None))
    assert cell.band is Band.NA
    assert cell.flags == ["constraint:impossible_pair"]


def test_NA_cong_executed_record_thi_raise():
    """Tính toàn vẹn của mẫu số là toàn bộ lý do module này tồn tại."""
    with pytest.raises(NAConflictError):
        project(constraint={"id": "impossible_pair"}, observation=obs())


def test_phan_tich_de_xuat_NA_cho_o_bat_kha_thi():
    """Phân tích tĩnh thấy một ô không thể tồn tại thì ô đó rời khỏi mẫu số,
    kèm cờ riêng để soát lại được ở report."""
    cell = project(proposal={"na_reason": "hai giá trị loại trừ nhau trong chữ ký hàm"})
    assert cell.band is Band.NA
    assert cell.flags == ["na_from_analysis"]


# ─────────────────────────── thứ tự nhánh ───────────────────────────


def test_unresolved_khong_bao_gio_pass():
    cell = project(observation=obs(outcome="unresolved"))
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["unresolved_probe"]


def test_artifact_khong_khop_probe_sha256():
    cell = project(observation=obs(artifact_probe_sha256="sha-khac"))
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["probe_binding_mismatch"]


def test_binding_mismatch_dung_truoc_ca_exit_code():
    """Artifact không neo được thì không làm chứng cho pass HAY fail."""
    cell = project(observation=obs(artifact_probe_sha256="sha-khac", test_exit_code=1))
    assert cell.flags == ["probe_binding_mismatch"]


def test_probe_fail_la_low_kem_co_khong_phai_unknown():
    cell = project(observation=obs(test_exit_code=1))
    assert cell.band is Band.LOW
    assert cell.flags == ["known_failure"]


def test_cov_cell_co_dong_vang_trong_cov_suite():
    cell = project(observation=obs(cov_cell={"src/cart.py:42", "src/ma_khac.py:9"}))
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["coverage_inconsistent"]


def test_pass_ma_khong_dau_cham_toi_code_path():
    cell = project(observation=obs(cov_cell=set(), cov_suite=set()))
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["coverage_mismatch"]


def test_chi_suite_cham_thi_la_incidental():
    cell = project(observation=obs(cov_cell=set()))
    assert cell.band is Band.LOW
    assert cell.flags == ["incidental"]


def test_khong_assert_nao():
    cell = project(observation=obs(assert_count=0))
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["no_assertion"]


def test_dung_mot_assert_la_med():
    cell = project(observation=obs(assert_count=1))
    assert cell.band is Band.MED
    assert cell.flags == []


def test_duoi_bar_da_siet_boi_calibration():
    cell = project(observation=obs(assert_count=2, calibration_min_asserts=3))
    assert cell.band is Band.MED
    assert cell.flags == ["high_bar_tightened"]


# ─────────────────── zone chặn: high phải có mutant bị giết ───────────────────


def test_zone_chan_du_dieu_kien_thi_high():
    cell = project(observation=obs())
    assert cell.band is Band.HIGH
    assert cell.flags == []
    assert cell.source == "projected"


def test_zone_chan_thieu_mutation_run():
    cell = project(observation=obs(mutation_run=None))
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["mutation_missing"]


def test_zone_chan_mutant_song_sot_la_false_high():
    cell = project(
        observation=obs(mutation_run={"verdict": "survived", "seed_id": "seed-1"})
    )
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["mutant_survived"]


def test_zone_chan_killed_nhung_binding_thieu_truong():
    thieu = dict(BINDING)
    del thieu["operator"]
    cell = project(
        observation=obs(
            mutation_run={"verdict": "killed", "seed_id": "seed-1", "binding": thieu}
        )
    )
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["mutation_missing", "mutation_unbound"]


def test_zone_chan_cung_vong_seed_da_survived_roi_moi_killed():
    cell = project(
        observation=obs(
            mutation_run={
                "verdict": "killed",
                "seed_id": "seed-1",
                "binding": dict(BINDING),
                "round_had_survived": True,
            }
        )
    )
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["mutant_survived", "mutation_round_conflict"]


def test_zone_chan_killed_lech_seed_cua_vong_calibration_hien_tai():
    cell = project(
        observation=obs(
            mutation_run={
                "verdict": "killed",
                "seed_id": "seed-cu",
                "binding": dict(BINDING),
            }
        )
    )
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["mutation_missing"]


def test_zone_khong_chan_lay_mau_va_khai_ra_dieu_do():
    cell = project(zone=ZONE_COLD, observation=obs(mutation_run=None))
    assert cell.band is Band.HIGH
    assert cell.flags == ["mutation_sampled"]


# ─────────────────────────── hàng DEFAULT ───────────────────────────


def test_khong_co_record_nao_thi_unknown():
    cell = project(observation=None)
    assert cell.band is Band.UNKNOWN
    assert cell.flags == []


def test_stub_con_song_che_dung_hang_default():
    cell = project(observation={"stub_alive": True})
    assert cell.band is Band.STUB
    assert cell.flags == ["stubbed"]


def test_stub_KHONG_che_mot_o_unknown_dang_mang_co():
    """`stub` nghĩa là "chưa ai nhìn"; cờ nghĩa là "đã nhìn và thấy có vấn đề".
    Che cái sau bằng cái trước là đổi một phát hiện thành một khoản nợ đã duyệt."""
    cell = project(observation=obs(outcome="unresolved", stub_alive=True))
    assert cell.band is Band.UNKNOWN
    assert cell.flags == ["unresolved_probe"]

    song_sot = project(
        observation=obs(
            mutation_run={"verdict": "survived", "seed_id": "seed-1"}, stub_alive=True
        )
    )
    assert song_sot.band is Band.UNKNOWN
    assert song_sot.flags == ["mutant_survived"]


# ─────────────────────────── bất biến chung ───────────────────────────


@pytest.mark.parametrize(
    "kwargs",
    [
        {"observation": None},
        {"observation": obs()},
        {"observation": obs(test_exit_code=1)},
        {"constraint": {"id": "x"}, "observation": None},
    ],
)
def test_source_luon_la_projected(kwargs):
    assert project(**kwargs).source == "projected"


def test_band_khong_bao_gio_nhan_tu_ben_ngoai():
    """Không có tham số `band` nào trong chữ ký: band là DERIVED, không bao giờ
    do model chọn."""
    import inspect

    assert "band" not in inspect.signature(project_cell).parameters
