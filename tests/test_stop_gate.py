"""Bộ kiểm của stop gate — 9 điều kiện chặn phát hành.

Mỗi điều kiện (a)–(i) có ÍT NHẤT một ca chặn và một ca không chặn, đi qua cùng
một hàm. Lý do phải làm đủ cả hai chiều: một cổng mà tập giá trị trả về khả dĩ
chỉ có một phần tử thì nó không phải cổng, nó là một cái ống — và cách duy nhất
để biết là chạy nó ở cả hai phía.

Phần đắt nhất của tệp này là `test_point_estimate_passes_where_the_interval_blocks`:
nó ghim đúng chỗ ba tài liệu nền không nối được với nhau.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.contracts.errors import ConfigError  # noqa: E402
from app.gates.registry import GateContext, load_gates_config, run_stop_gate  # noqa: E402
from app.gates.stop_gate import (  # noqa: E402
    CellRef,
    DefectRef,
    ReleasePassForbidden,
    StopGateInput,
    StopGateResult,
    assert_release_pass,
)
from test_gates import drop_key, reference_wilson_lower, with_op  # noqa: E402

BLOCKING_W = 0.7  # đọc từ config/zones.yaml ở đời thật; ở đây là tham số vào


def ctx(config: dict[str, Any] | None = None, wilson: Any = None) -> GateContext:
    return GateContext(
        config=load_gates_config() if config is None else config,
        wilson_lower=reference_wilson_lower if wilson is None else wilson,
    )


def clean_input(**overrides: Any) -> StopGateInput:
    """Một lượt chạy KHÔNG chạm điều kiện chặn nào.

    Tồn tại để mỗi phép kiểm phía dưới chỉ đổi đúng MỘT thứ: nếu ca nền không
    xanh thì mọi ca đỏ phía sau đều vô nghĩa, vì không biết cái gì làm nó đỏ.
    """
    base: dict[str, Any] = {
        "stop_hook_active": False,
        "bypass_reason": None,
        "blocking_w": BLOCKING_W,
        "cells": [
            CellRef(
                id="cell:flow=checkout|net=slow",
                zone_id="zone:checkout",
                zone_w=0.9,
                band="high",
                declared=True,
                mutation_killed_matches_seed=True,
            ),
            CellRef(
                id="cell:flow=browse|net=fast",
                zone_id="zone:browse",
                zone_w=0.2,
                band="unknown",
                declared=True,
            ),
        ],
        "defects": [DefectRef(id="D-1", zone_id="zone:checkout", reference="PR-4417")],
        "false_high_killed": 35,
        "false_high_survived": 0,
        "declared_digest": "sha256:9338",
        "observed_digest": "sha256:9338",
        "chain_intact": True,
        "governance_hash_match": True,
        "cross_check_counts": {"ledger": 10, "transcript": 10},
        "transcript_parsed": True,
        "bin_manifest_match": True,
        "axis_drift_values": [],
        "class_b_mutation_catch": 1.0,
        "small_scope_verified": True,
        "interleaving_unknown_after_saturation": 0,
        "calibration_lock_present": True,
    }
    base.update(overrides)
    return StopGateInput(**base)


def codes(result: StopGateResult) -> set[str]:
    return {r.code for r in result.reasons}


# ───────────────────────── ca nền ─────────────────────────


def test_clean_run_is_not_blocked_and_may_print_release_pass() -> None:
    result = run_stop_gate(clean_input(), ctx())

    assert result.blocked is False
    assert result.reasons == []
    assert result.bypassed is False
    assert result.release_pass_allowed is True
    assert result.denominator == 1
    assert_release_pass(result)  # không được raise


# ───────────────────────── (a) ─────────────────────────


def test_a_unknown_cell_without_a_live_stub_in_a_blocking_zone_blocks() -> None:
    result = run_stop_gate(
        clean_input(
            cells=[
                CellRef(
                    id="cell:flow=checkout|net=slow",
                    zone_id="zone:checkout",
                    zone_w=0.9,
                    band="unknown",
                    stub_alive=False,
                    declared=True,
                )
            ]
        ),
        ctx(),
    )
    assert result.blocked is True
    assert "STOP-A" in codes(result)


def test_a_unknown_cell_with_a_live_stub_does_not_block() -> None:
    result = run_stop_gate(
        clean_input(
            cells=[
                CellRef(
                    id="cell:flow=checkout|net=slow",
                    zone_id="zone:checkout",
                    zone_w=0.9,
                    band="unknown",
                    stub_alive=True,
                    declared=True,
                )
            ]
        ),
        ctx(),
    )
    assert "STOP-A" not in codes(result)


def test_a_low_weight_zone_may_hold_a_declared_unknown() -> None:
    """Zone `w` thấp được phép `unknown` KHI ĐÃ KHAI — im lặng mới là vi phạm."""
    declared = run_stop_gate(clean_input(), ctx())
    assert "STOP-A" not in codes(declared)
    assert "STOP-D" not in codes(declared)

    silent_cells = list(clean_input().cells)
    silent_cells[1] = silent_cells[1].model_copy(update={"declared": False})
    silent = run_stop_gate(clean_input(cells=silent_cells), ctx())
    assert "STOP-D" in codes(silent)


def test_a_boundary_zone_weight_equal_to_blocking_w_is_inside_the_blocking_set() -> None:
    """Ca BIÊN của tập chặn: `w == blocking_w` NẰM TRONG tập chặn.

    Dấu `>=` ở đây là ĐỊNH NGHĨA của tập chặn (thuộc `config/zones.yaml`), không
    phải một ngưỡng của gate — nhưng nó vẫn phải có ca biên, vì một zone rơi ra
    khỏi tập chặn là đúng cách một lượt chạy thoát khỏi release block.
    """
    at_boundary = clean_input(
        cells=[
            CellRef(
                id="cell:x",
                zone_id="zone:edge",
                zone_w=BLOCKING_W,
                band="unknown",
                declared=True,
            )
        ]
    )
    below = clean_input(
        cells=[
            CellRef(
                id="cell:x",
                zone_id="zone:edge",
                zone_w=BLOCKING_W - 0.01,
                band="unknown",
                declared=True,
            )
        ]
    )

    assert "STOP-A" in codes(run_stop_gate(at_boundary, ctx()))
    assert "STOP-A" not in codes(run_stop_gate(below, ctx()))


# ───────────────────────── (b) — Wilson ─────────────────────────


def test_b_high_false_high_rate_blocks_and_reports_both_numbers() -> None:
    result = run_stop_gate(
        clean_input(false_high_killed=10, false_high_survived=30), ctx()
    )
    detail = next(r.detail for r in result.reasons if r.code == "STOP-B")

    assert result.blocked is True
    assert "n=40" in detail
    assert "point=0.7500" in detail
    assert "biên dưới Wilson" in detail
    assert result.false_high_lower is not None
    assert result.false_high_lower == pytest.approx(reference_wilson_lower(30, 40), abs=1e-12)


def test_b_clean_calibration_with_enough_samples_does_not_block() -> None:
    result = run_stop_gate(clean_input(false_high_killed=35, false_high_survived=0), ctx())
    assert "STOP-B" not in codes(result)
    assert result.false_high_lower == 0.0


def test_b_point_estimate_passes_where_the_interval_blocks() -> None:
    """Ca dạy học đắt nhất của cả workshop.

    `{killed: 2, survived: 0}` cho point estimate `0.0000` — đọc thành "sạch" và
    ĐI LỌT. Wilson95 của `0/2` là `[0.0000, 0.6576]`: tỉ lệ chấm-cao-sai thật có
    thể tới 65,8%, hơn bốn lần trần 0.15. Ở cỡ mẫu 2 KHÔNG kết luận nào được rút
    ra, nên lượt chạy đó là UNVERIFIED, và UNVERIFIED thì chặn.
    """
    looks_clean = clean_input(false_high_killed=2, false_high_survived=0)
    assert looks_clean.false_high_survived / (
        looks_clean.false_high_killed + looks_clean.false_high_survived
    ) == 0.0  # point estimate nói "sạch"

    result = run_stop_gate(looks_clean, ctx())
    detail = next(r.detail for r in result.reasons if r.code == "STOP-B")

    assert result.blocked is True
    assert "UNVERIFIED" in detail
    assert "n=2" in detail


def test_b_the_historical_record_blocks_for_the_right_reason() -> None:
    """`{killed: 0, survived: 2, rate: 1.0}` — bản ghi thật của tài liệu nền."""
    result = run_stop_gate(clean_input(false_high_killed=0, false_high_survived=2), ctx())
    detail = next(r.detail for r in result.reasons if r.code == "STOP-B")

    assert result.blocked is True
    assert "UNVERIFIED" in detail, (
        "rate=1.0 trên n=2 chặn đúng, nhưng lý do đúng là CỠ MẪU chưa nói được gì, "
        "không phải 'đã đo được là tệ'"
    )


def test_b_empty_calibration_denominator_is_red() -> None:
    result = run_stop_gate(clean_input(false_high_killed=0, false_high_survived=0), ctx())
    assert result.blocked is True
    assert "STOP-B" in codes(result)
    assert result.false_high_lower is None


def test_b_boundary_case_is_decided_by_compare_op() -> None:
    """Ca BIÊN: biên dưới Wilson bằng ĐÚNG `false_high_block`."""
    threshold = load_gates_config()["stop_gate"]["false_high_block"]
    exact = clean_input(false_high_killed=35, false_high_survived=5)

    lenient = run_stop_gate(
        exact, ctx(with_op("stop_gate", "<="), wilson=lambda k, n, conf: threshold)
    )
    strict = run_stop_gate(
        exact, ctx(with_op("stop_gate", "<"), wilson=lambda k, n, conf: threshold)
    )

    assert "STOP-B" not in codes(lenient)
    assert lenient.compare_op == "<="
    assert "STOP-B" in codes(strict)
    assert strict.compare_op == "<"


def test_b_missing_config_key_names_itself() -> None:
    with pytest.raises(ConfigError) as exc:
        run_stop_gate(clean_input(), ctx(drop_key("stop_gate.false_high_block")))
    assert exc.value.key == "stop_gate.false_high_block"

    with pytest.raises(ConfigError) as exc:
        run_stop_gate(clean_input(), ctx(drop_key("stop_gate.false_high_min_n")))
    assert exc.value.key == "stop_gate.false_high_min_n"


# ───────────────────────── (c) ─────────────────────────


def test_c_defect_in_a_blocking_zone_without_a_reference_blocks() -> None:
    result = run_stop_gate(
        clean_input(defects=[DefectRef(id="D-9", zone_id="zone:checkout", reference="  ")]),
        ctx(),
    )
    assert "STOP-C" in codes(result)


def test_c_defect_with_a_reference_does_not_block() -> None:
    assert "STOP-C" not in codes(run_stop_gate(clean_input(), ctx()))


def test_c_defect_pointing_at_an_unknown_zone_blocks() -> None:
    result = run_stop_gate(
        clean_input(defects=[DefectRef(id="D-9", zone_id="zone:khong-co", reference="PR-1")]),
        ctx(),
    )
    assert "STOP-C" in codes(result)


# ───────────────────────── (d) ─────────────────────────


def test_d_digest_mismatch_blocks() -> None:
    result = run_stop_gate(clean_input(observed_digest="sha256:khac"), ctx())
    assert "STOP-D" in codes(result)


def test_d_missing_governance_lock_digest_blocks() -> None:
    result = run_stop_gate(clean_input(declared_digest=None), ctx())
    assert "STOP-D" in codes(result)


def test_d_stale_cell_outside_the_declared_set_blocks() -> None:
    cells = list(clean_input().cells)
    cells[0] = cells[0].model_copy(update={"stale": True, "declared": False})
    result = run_stop_gate(clean_input(cells=cells), ctx())
    assert "STOP-D" in codes(result)


# ───────────────────────── (e) ─────────────────────────


@pytest.mark.parametrize(
    "override",
    [
        {"chain_intact": False},
        {"chain_intact": None},
        {"governance_hash_match": False},
        {"governance_hash_match": None},
        {"transcript_parsed": False},
        {"transcript_parsed": None},
        {"cross_check_counts": None},
        {"cross_check_counts": {"ledger": 10, "transcript": 9}},
    ],
)
def test_e_any_missing_or_broken_witness_blocks(override: dict[str, Any]) -> None:
    """Fail-closed: "chưa đo được" và "đo được và ổn" là hai chuyện khác nhau."""
    result = run_stop_gate(clean_input(**override), ctx())
    assert result.blocked is True
    assert "STOP-E" in codes(result)


def test_e_intact_witness_does_not_block() -> None:
    assert "STOP-E" not in codes(run_stop_gate(clean_input(), ctx()))


# ───────────────────────── (f) (g) ─────────────────────────


@pytest.mark.parametrize("value", [False, None])
def test_f_bin_manifest_mismatch_blocks(value: Any) -> None:
    assert "STOP-F" in codes(run_stop_gate(clean_input(bin_manifest_match=value), ctx()))


def test_f_matching_manifest_does_not_block() -> None:
    assert "STOP-F" not in codes(run_stop_gate(clean_input(), ctx()))


def test_g_axis_drift_blocks() -> None:
    result = run_stop_gate(clean_input(axis_drift_values=["net=offline"]), ctx())
    assert "STOP-G" in codes(result)


def test_g_no_drift_does_not_block() -> None:
    assert "STOP-G" not in codes(run_stop_gate(clean_input(), ctx()))


# ───────────────────────── (h) ─────────────────────────


@pytest.mark.parametrize(
    "override",
    [
        {"class_b_mutation_catch": 0.99},
        {"class_b_mutation_catch": None},
        {"small_scope_verified": False},
        {"small_scope_verified": None},
        {"interleaving_unknown_after_saturation": 1},
    ],
)
def test_h_class_b_gaps_block(override: dict[str, Any]) -> None:
    result = run_stop_gate(clean_input(**override), ctx())
    assert "STOP-H" in codes(result)


def test_h_boundary_mutation_catch_exactly_at_the_floor_does_not_block() -> None:
    """Ca BIÊN: `class_b_mutation_catch == floor` (1.0) là ĐẠT."""
    floor = load_gates_config()["stop_gate"]["class_b_mutation_catch_floor"]
    assert "STOP-H" not in codes(run_stop_gate(clean_input(class_b_mutation_catch=floor), ctx()))
    assert "STOP-H" in codes(
        run_stop_gate(clean_input(class_b_mutation_catch=floor - 1e-9), ctx())
    )


# ───────────────────────── (i) ─────────────────────────


def test_i_an_empty_blocking_set_is_itself_a_block() -> None:
    """Tập-ô-bị-chặn RỖNG cũng là chặn — và mẫu số 0 là ĐỎ, không phải xanh."""
    result = run_stop_gate(
        clean_input(
            cells=[
                CellRef(id="cell:x", zone_id="zone:browse", zone_w=0.2, band="high", declared=True)
            ],
            defects=[],
        ),
        ctx(),
    )
    assert result.blocked is True
    assert "STOP-I" in codes(result)
    assert result.denominator == 0
    assert result.release_pass_allowed is False


def test_i_missing_calibration_lock_blocks() -> None:
    result = run_stop_gate(clean_input(calibration_lock_present=False), ctx())
    assert "STOP-I" in codes(result)


def test_i_high_cell_without_a_matching_killed_mutant_blocks() -> None:
    cells = list(clean_input().cells)
    cells[0] = cells[0].model_copy(update={"mutation_killed_matches_seed": False})
    result = run_stop_gate(clean_input(cells=cells), ctx())
    assert "STOP-I" in codes(result)


def test_i_fully_backed_blocking_set_does_not_block() -> None:
    assert "STOP-I" not in codes(run_stop_gate(clean_input(), ctx()))


# ───────────────────────── (0) bypass ─────────────────────────


def test_0_bypass_records_once_and_forbids_release_pass_forever() -> None:
    blocked_run = clean_input(
        stop_hook_active=True,
        bypass_reason="hotfix sự cố P0, có phê duyệt của trực ca",
        bin_manifest_match=False,
        axis_drift_values=["net=offline"],
    )
    result = run_stop_gate(blocked_run, ctx())

    assert result.bypassed is True
    assert result.blocked is False
    assert result.release_pass_allowed is False
    assert len(result.records) == 1, "lý do phải được ghi ĐÚNG MỘT lần"
    assert result.records[0]["type"] == "gate_bypassed"
    assert "hotfix" in result.records[0]["reason"]
    assert {"STOP-F", "STOP-G"} <= set(result.records[0]["blocked_reasons"])

    with pytest.raises(ReleasePassForbidden):
        assert_release_pass(result)


def test_0_bypass_still_re_derives_every_condition() -> None:
    """Bypass cho đi qua, KHÔNG cho khỏi bị soi."""
    result = run_stop_gate(
        clean_input(
            stop_hook_active=True,
            bypass_reason="sự cố sản xuất",
            calibration_lock_present=False,
            chain_intact=False,
        ),
        ctx(),
    )
    assert {"STOP-E", "STOP-I"} <= codes(result)


def test_0_bypass_costs_the_release_pass_even_on_a_clean_run() -> None:
    result = run_stop_gate(
        clean_input(stop_hook_active=True, bypass_reason="diễn tập quy trình"), ctx()
    )
    assert result.reasons == []
    assert result.bypassed is True
    assert result.release_pass_allowed is False
    with pytest.raises(ReleasePassForbidden):
        assert_release_pass(result)


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_0_bypass_without_a_reason_is_refused(reason: str | None) -> None:
    """"In lý do MỘT lần rồi cho qua" — không có lý do thì không có cửa nào."""
    result = run_stop_gate(
        clean_input(stop_hook_active=True, bypass_reason=reason), ctx()
    )
    assert result.bypassed is False
    assert result.blocked is True
    assert "STOP-BYPASS-NO-REASON" in codes(result)
    assert result.records == []


def test_blocked_run_can_never_print_release_pass() -> None:
    result = run_stop_gate(clean_input(bin_manifest_match=False), ctx())
    assert result.release_pass_allowed is False
    with pytest.raises(ReleasePassForbidden):
        assert_release_pass(result)


def test_all_nine_conditions_are_reachable_in_one_run() -> None:
    """Tập lý do đến được phải có đủ 9 mã, không phải một mã duy nhất.

    Đây là phép kiểm chống đúng hình dạng đã đo được: "không một nhánh mã nào
    trả về 'fail'", tức tập giá trị khả dĩ chỉ có một phần tử.
    """
    everything_wrong = clean_input(
        cells=[
            CellRef(
                id="cell:a",
                zone_id="zone:checkout",
                zone_w=0.9,
                band="unknown",
                stub_alive=False,
                declared=False,
            ),
            CellRef(
                id="cell:b",
                zone_id="zone:checkout",
                zone_w=0.9,
                band="high",
                declared=True,
                mutation_killed_matches_seed=False,
            ),
        ],
        defects=[DefectRef(id="D-1", zone_id="zone:checkout", reference=None)],
        false_high_killed=0,
        false_high_survived=2,
        observed_digest="sha256:lech",
        chain_intact=False,
        bin_manifest_match=False,
        axis_drift_values=["net=offline"],
        class_b_mutation_catch=0.5,
        calibration_lock_present=False,
    )
    result = run_stop_gate(everything_wrong, ctx())

    assert codes(result) == {
        "STOP-A",
        "STOP-B",
        "STOP-C",
        "STOP-D",
        "STOP-E",
        "STOP-F",
        "STOP-G",
        "STOP-H",
        "STOP-I",
    }
    assert result.blocked is True
