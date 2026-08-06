"""Gate 2a — đọc phán quyết của lưới.

Gate này đọc NỘI DUNG phán quyết, không đọc SỰ CÓ MẶT của tạo tác. Hình dạng bị
cấm ở đây là một bước CI chỉ kiểm `os.path.exists("coverage.json")` rồi tự khai
trong chính docstring của mình rằng "the coverage-grid VERDICT is never read
here".

Hai luật còn lại:

- Zone chặn VẮNG khỏi `min_per_zone` là ĐỎ. Đã đo được ca một N/A duy nhất trên
  zone nặng nhất (w=0.95) làm zone đó rời khỏi chính con số LÀ cái gate, và lượt
  chạy báo PASS mà không chỗ nào nói có một zone đã ra đi.
- Chỉ đọc `min_per_zone`. `risk_weighted_coverage` là số chẩn đoán, và một trung
  bình cho phép một zone cao che một zone thấp ở chỗ hoàn toàn khác.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol

from app.contracts.types import EvidenceTier, Finding, GateName, GateVerdict

if TYPE_CHECKING:
    from app.gates.registry import GateContext

_OP_KEY = "grid.compare_op"


class GridReviewVerdictLike(Protocol):
    """Hợp đồng tối thiểu mà `core/grid` phải cấp cho gate này.

    Khai bằng Protocol thay vì import thẳng `GridReviewVerdict` vì `core/grid`
    thuộc lô build khác; đây là hình dạng ĐƯỢC KIỂM, không phải hình dạng được
    hy vọng — thiếu bất kỳ thuộc tính nào dưới đây thì gate CHẶN chứ không nổ
    `AttributeError` giữa chừng.
    """

    risk_band: str
    cells_total: int
    cells_scored: int
    blocking_zones: Sequence[str]
    min_per_zone: Mapping[str, float]
    source_file: str
    source_line: int


def _zone_score(value: object) -> float | None:
    """Rút điểm band tệ nhất của một zone.

    Nhận cả hai hình dạng: một số trần, hoặc bản tóm tắt per-zone mà
    `core.grid.rollup.min_per_zone()` trả về (`{"worst_score": ..., "w": ...}`).
    Hình dạng lạ trả `None` để gọi bên trên biến nó thành một phát hiện, chứ
    KHÔNG đoán bừa một con số — đoán một điểm band là tự cấp cho mình quyền
    phán xử mà module này không có.
    """
    if isinstance(value, Mapping):
        if "worst_score" not in value:
            return None
        value = value["worst_score"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


_REQUIRED_ATTRS: tuple[str, ...] = (
    "risk_band",
    "cells_total",
    "cells_scored",
    "blocking_zones",
    "min_per_zone",
    "source_file",
    "source_line",
)


def check_grid(ctx: GateContext) -> GateVerdict:
    """Chấm cổng `grid`."""
    if ctx.grid_verdict is None:
        return ctx.refuse(
            GateName.GRID, "không có phán quyết lưới nào được truyền vào", _OP_KEY
        )

    verdict = ctx.grid_verdict
    missing_attrs = [name for name in _REQUIRED_ATTRS if not hasattr(verdict, name)]
    if missing_attrs:
        return ctx.refuse(
            GateName.GRID,
            f"phán quyết lưới thiếu trường bắt buộc: {missing_attrs}",
            _OP_KEY,
        )

    min_band_score = ctx.require("grid.min_band_score")
    skip_on_bands = list(ctx.require("grid.skip_on_bands"))

    if verdict.risk_band in skip_on_bands:
        _, op = ctx.compare_by(0.0, min_band_score, _OP_KEY)
        return GateVerdict(
            gate=GateName.GRID,
            verdict="pass",
            evidence_tier=None,
            findings=[],
            compare_op=op,
            denominator=verdict.cells_scored,
            blocked=False,
            skipped=True,
            reason=(
                f"band rủi ro {verdict.risk_band!r} nằm trong grid.skip_on_bands="
                f"{skip_on_bands} — bỏ qua có khai báo, không phải bỏ qua trong im lặng"
            ),
        )

    findings: list[Finding] = []

    if not list(verdict.blocking_zones):
        findings.append(
            Finding(
                rule_id="GRID-EMPTY-BLOCKING-SET",
                severity="error",
                file=verdict.source_file,
                line=verdict.source_line,
                finding=(
                    "tập zone chặn RỖNG — bên bị chấm không được phép làm rỗng tập chặn; "
                    "tập chặn rỗng là lỗi cấu hình, không phải một kết quả tốt"
                ),
            )
        )
        _, op = ctx.compare_by(0.0, min_band_score, _OP_KEY)
        return GateVerdict(
            gate=GateName.GRID,
            verdict="fail",
            evidence_tier=EvidenceTier.DERIVED,
            findings=findings,
            compare_op=op,
            denominator=verdict.cells_scored,
            blocked=True,
            reason="không có zone nào thuộc tập chặn",
        )

    if verdict.cells_scored == 0:
        return ctx.refuse(
            GateName.GRID,
            "cells_scored=0 — mọi ô đã bị loại; 'không có dữ liệu' không phải 'đo được và bằng 0'",
            _OP_KEY,
        )

    scores: list[float] = []
    for zone_id in verdict.blocking_zones:
        if zone_id not in verdict.min_per_zone:  # noqa: SIM118 - Mapping, không phải dict
            findings.append(
                Finding(
                    rule_id="GRID-ZONE-MISSING",
                    severity="error",
                    file=verdict.source_file,
                    line=verdict.source_line,
                    finding=(
                        f"zone chặn {zone_id!r} không có mục trong min_per_zone — "
                        f"một zone rời khỏi con số vốn LÀ cái gate là ĐỎ, không phải bỏ qua"
                    ),
                )
            )
            continue

        score = _zone_score(verdict.min_per_zone[zone_id])
        if score is None:
            findings.append(
                Finding(
                    rule_id="GRID-ZONE-UNREADABLE",
                    severity="error",
                    file=verdict.source_file,
                    line=verdict.source_line,
                    finding=(
                        f"mục min_per_zone[{zone_id!r}] không đọc được thành điểm band "
                        f"({verdict.min_per_zone[zone_id]!r}) — từ chối đoán"
                    ),
                )
            )
            continue

        scores.append(score)
        zone_ok, op = ctx.compare_by(score, min_band_score, _OP_KEY)
        if not zone_ok:
            findings.append(
                Finding(
                    rule_id="GRID-ZONE-BELOW-FLOOR",
                    severity="error",
                    file=verdict.source_file,
                    line=verdict.source_line,
                    finding=(
                        f"zone chặn {zone_id!r} có ô tệ nhất band_score={score}, "
                        f"sàn đòi {op} {min_band_score}"
                    ),
                )
            )

    measured = min(scores) if scores else 0.0
    floor_ok, op = ctx.compare_by(measured, min_band_score, _OP_KEY)
    ok = floor_ok and not any(f.severity == "error" for f in findings)

    return GateVerdict(
        gate=GateName.GRID,
        verdict="pass" if ok else "fail",
        evidence_tier=EvidenceTier.DERIVED,
        findings=findings,
        compare_op=op,
        denominator=verdict.cells_scored,
        blocked=not ok,
        reason=(
            f"zone chặn tệ nhất={measured} {op} {min_band_score}; "
            f"đã chấm {verdict.cells_scored}/{verdict.cells_total} ô"
        ),
    )
