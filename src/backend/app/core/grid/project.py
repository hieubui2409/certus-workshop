"""Bảng band projection — trái tim của hệ.

LUẬT SỐ MỘT: *"a grid cell's band is DERIVED, never asserted, never model-chosen."*
`source` chỉ nhận đúng một giá trị: `"projected"`.

If-chain THUẦN, và THỨ TỰ NHÁNH LÀ LOAD-BEARING. Bảng phải TOÀN PHẦN: mọi quan sát
rơi vào đúng một hàng, hàng cuối là DEFAULT nên không đầu vào nào rơi ra ngoài.
Đổi chỗ hai nhánh trong file này là đổi ngữ nghĩa của band, không phải dọn code.

Neo tài liệu: research note 02 §3.1 (bảng 17 hàng), §3.3 (N/A), §4.1 (mutation).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.contracts.errors import NAConflictError
from app.contracts.types import Band, Cell
from app.core.grid.cells import load_grid_config, require_key
from app.core.grid.zones import Zone

_SOURCE = "grid.yaml"

#: Quan sát về một ô: kết quả probe + coverage + assert + mutation. Dict thuần vì
#: nó được ghép từ bốn nguồn artifact khác nhau và không nguồn nào biết đủ.
Observation = Mapping[str, Any]


@dataclass(frozen=True)
class ProjectionParams:
    min_independent_asserts_for_high: int
    mutation_binding_fields: tuple[str, ...]


def load_projection_params(*, config_dir: Path | None = None) -> ProjectionParams:
    cfg = load_grid_config(config_dir=config_dir)
    fields = require_key(cfg, "projection.mutation_binding_fields", source=_SOURCE)
    return ProjectionParams(
        min_independent_asserts_for_high=int(
            require_key(
                cfg, "projection.min_independent_asserts_for_high", source=_SOURCE
            )
        ),
        mutation_binding_fields=tuple(str(f) for f in fields),
    )


def _has_executed_record(observation: Observation | None) -> bool:
    """Ô này đã có lệnh nào thật sự chạy trên nó chưa."""
    if not observation:
        return False
    return observation.get("test_exit_code") is not None


def _is_bound(mutation_run: Mapping[str, Any] | None, params: ProjectionParams) -> bool:
    """Binding đủ 5 trường mới coi là neo được vào ô này.

    Thiếu một trường thì record vẫn tồn tại và vẫn đọc như một record hợp lệ —
    khác biệt duy nhất là nó không chứng minh được nó nói về ô NÀO.
    """
    if not mutation_run:
        return False
    binding = mutation_run.get("binding") or {}
    return all(binding.get(field) for field in params.mutation_binding_fields)


def project_cell(
    *,
    cell_id: str,
    axes: Mapping[str, str],
    zone: Zone,
    blocking_w: float,
    observation: Observation | None = None,
    constraint: Mapping[str, Any] | None = None,
    proposal: Mapping[str, Any] | None = None,
    params: ProjectionParams | None = None,
    config_dir: Path | None = None,
) -> Cell:
    """Suy ra band của một ô từ quan sát. Không bao giờ nhận band từ bên ngoài."""
    params = params or load_projection_params(config_dir=config_dir)
    obs: Observation = observation or {}
    zone_id = str(zone["id"])
    zone_w = float(zone["w"])
    blocking = zone_w >= blocking_w
    evidence: list[str] = list(obs.get("evidence_id") or [])

    def cell(band: Band, flags: Sequence[str] = ()) -> Cell:
        return Cell(
            id=cell_id,
            axes=dict(axes),
            zone_id=zone_id,
            zone_w=zone_w,
            band=band,
            source="projected",
            flags=list(flags),
            evidence_id=evidence,
        )

    # ── hàng 0: N/A đã qua admit_constraint. N/A THẮNG TRƯỚC mọi thứ ──────────
    # N/A không phải một mức phủ thấp; nó là lời khai rằng ô này KHÔNG THUỘC mẫu
    # số. Vì thế nó phải được xét trước khi bất kỳ quan sát nào được đọc.
    if constraint:
        if _has_executed_record(obs):
            raise NAConflictError(
                f"{cell_id}: constraint {constraint.get('id')!r} khai N/A nhưng ô có "
                f"executed record (exit_code={obs.get('test_exit_code')}). Tính toàn "
                f"vẹn của mẫu số là toàn bộ lý do module này tồn tại."
            )
        return cell(Band.NA, [f"constraint:{constraint.get('id')}"])

    # Phân tích tĩnh của model có thể thấy một ô bất khả thi mà constraint chưa
    # kịp khai (ví dụ hai giá trị loại trừ nhau ngay trong chữ ký hàm). Ghi cờ
    # riêng để soát lại được ở report.
    if proposal and proposal.get("na_reason"):
        return cell(Band.NA, ["na_from_analysis"])

    # ── hàng 1: outcome không phân giải được ⇒ KHÔNG BAO GIỜ pass ────────────
    # result.json thiếu/hỏng, nonce lệch: ta không biết probe đã chạy hay chưa,
    # nên mọi nhánh phía dưới (đều đọc exit code) đang đọc một con số vô nghĩa.
    if obs.get("outcome") == "unresolved":
        return cell(Band.UNKNOWN, ["unresolved_probe"])

    exit_code = obs.get("test_exit_code")
    if exit_code is None:
        return _default_row(cell, obs)

    # ── hàng 2: artifact không khớp probe_sha256 ─────────────────────────────
    # Một artifact không neo được vào chính probe này thì không làm chứng được
    # cho pass HAY fail — nên nhánh này đứng TRƯỚC nhánh đọc exit code.
    probe_sha = obs.get("probe_sha256")
    artifact_sha = obs.get("artifact_probe_sha256")
    if probe_sha and artifact_sha and probe_sha != artifact_sha:
        return cell(Band.UNKNOWN, ["probe_binding_mismatch"])

    # ── hàng 3: probe fail ───────────────────────────────────────────────────
    # "The exit status is the whole answer." Fail là một quan sát THẬT, nên `low`
    # kèm cờ chứ không phải `unknown`: ta biết ô này hỏng, không phải không biết gì.
    if exit_code != 0:
        return cell(Band.LOW, ["known_failure"])

    cov_cell = set(obs.get("cov_cell") or ())
    cov_suite = set(obs.get("cov_suite") or ())
    code_path = obs.get("code_path")

    # ── hàng 4: cov_cell chứa dòng KHÔNG có trong cov_suite ──────────────────
    # Hai report bất đồng nghĩa là ít nhất một cái đang nói về bản mã khác.
    if cov_cell - cov_suite:
        return cell(Band.UNKNOWN, ["coverage_inconsistent"])

    touched_by_cell = code_path in cov_cell
    touched_by_suite = code_path in cov_suite

    # ── hàng 5: pass nhưng KHÔNG đâu chạm tới code_path ──────────────────────
    if not touched_by_cell and not touched_by_suite:
        return cell(Band.UNKNOWN, ["coverage_mismatch"])

    # ── hàng 6: chỉ suite chạm, probe của ô thì không ────────────────────────
    # Dòng có chạy, nhưng do bài kiểm khác chạy nhờ — không ai đang canh ô này.
    if not touched_by_cell:
        return cell(Band.LOW, ["incidental"])

    assert_count = int(obs.get("assert_count") or 0)

    # ── hàng 7: pass + chạm, 0 assert ───────────────────────────────────────
    if assert_count == 0:
        return cell(Band.UNKNOWN, ["no_assertion"])

    # ── hàng 8: pass + chạm, đúng 1 assert ──────────────────────────────────
    if assert_count == 1:
        return cell(Band.MED)

    # ── hàng 9: dưới bar đã SIẾT bởi calibration ────────────────────────────
    # Calibration chỉ được siết lên, không bao giờ nới xuống; ô dưới bar mới rơi
    # `med` kèm cờ chứ không im lặng giữ `high` theo bar cũ.
    bar = obs.get("calibration_min_asserts")
    if bar is not None and assert_count < int(bar):
        return cell(Band.MED, ["high_bar_tightened"])

    if assert_count < params.min_independent_asserts_for_high:
        return cell(Band.MED)

    mutation_run = obs.get("mutation_run")

    if blocking:
        # ── hàng 10–14: zone chặn ⇒ MỌI ô `high` phải có mutant bị giết ──────
        # Không lấy mẫu, không ngoại lệ. Đây là chỗ đòn tautology chết: một probe
        # mà mọi assert đúng-hiển-nhiên vẫn bound + pass + chạm mọi dòng, nhưng
        # `high` trong zone chặn đơn giản KHÔNG TỒN TẠI như một nhánh tới được
        # của hàm này nếu thiếu mutant bị giết, neo seed, và bound đủ trường.
        if mutation_run and mutation_run.get("round_had_survived") and (
            mutation_run.get("verdict") == "killed"
        ):
            return cell(
                Band.UNKNOWN, ["mutant_survived", "mutation_round_conflict"]
            )
        if mutation_run and mutation_run.get("verdict") == "survived":
            # false_high: bài kiểm chạy, chạm, assert — và vẫn không bắt được lỗi.
            return cell(Band.UNKNOWN, ["mutant_survived"])
        if mutation_run and mutation_run.get("verdict") == "killed":
            if not _is_bound(mutation_run, params):
                return cell(
                    Band.UNKNOWN, ["mutation_missing", "mutation_unbound"]
                )
            run_seed = mutation_run.get("seed_id")
            cal_seed = obs.get("calibration_seed_id")
            # Neo seed phải HIỆN DIỆN và KHỚP. `None != None` là False, nên một
            # phép so sánh trần cho killed+bound mà THIẾU cả hai seed rơi thẳng
            # xuống HIGH — tức một `high` trong zone chặn không neo seed nào,
            # đúng thứ docstring hàng 10–14 khẳng định KHÔNG TỒN TẠI. Thiếu một
            # trong hai seed là fail-closed, không phải "coi như khớp".
            if run_seed is None or cal_seed is None or run_seed != cal_seed:
                return cell(Band.UNKNOWN, ["mutation_missing"])
            return cell(Band.HIGH)
        return cell(Band.UNKNOWN, ["mutation_missing"])

    # ── hàng 15: zone không chặn ⇒ mutation lấy mẫu theo seed ───────────────
    # Cờ ở đây không phải cảnh báo: nó nói rõ con số này dựa trên MẪU, để không
    # ai đọc nó như đã kiểm toàn phần.
    return cell(Band.HIGH, ["mutation_sampled"])


def _default_row(cell: Any, obs: Observation) -> Cell:
    """Hàng DEFAULT: không có record bound nào cho ô.

    STUB CHỈ CHE ĐÚNG HÀNG NÀY. Một ô `unknown` ĐANG MANG CỜ (mutant_survived,
    unresolved_probe, coverage_mismatch…) không bao giờ được stub che: `stub`
    nghĩa là "chưa ai nhìn và đã khai điều đó", còn cờ nghĩa là "đã nhìn và thấy
    có vấn đề". Che cái thứ hai bằng cái thứ nhất là đổi một phát hiện thành một
    khoản nợ được phê duyệt.
    """
    if obs.get("stub_alive"):
        return cell(Band.STUB, ["stubbed"])
    return cell(Band.UNKNOWN)
