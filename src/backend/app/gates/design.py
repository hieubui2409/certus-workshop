"""Gate 2 — ma trận phủ chiều chất lượng.

Ba luật riêng của gate này, và cả ba đều là phản ứng với một lỗi ĐÃ ĐO ĐƯỢC:

1. Ô không có quyết định là DEFECT, không phải "đã phủ" (`silent_na`).
2. Chính sách N/A khai theo TỪNG danh mục, vì hai chuẩn quốc tế nói ngược nhau:
   OWASP ASVS bắt buộc khai lý do, WCAG 2.2 cho phép im lặng. Áp một hằng số
   toàn hệ là khai luật của nhà như thể là yêu cầu của chuẩn ngoài.
3. Mỗi đường bắt buộc phải có một dòng test HOẶC một câu `N/A because ...`;
   "Paths present but silently uncovered = matrix rejected at Design Gate".

Giới hạn phải nói thẳng: sàn ở đây đếm ĐẶC TÍNH. Đã đo được ca lỗi rơi ở
sub-property, nơi không có hàng nào để mà bỏ trống — nâng sàn không hẹp lỗ đó đi
một milimet nào. Cái vá được lỗ đó là danh mục có thêm hàng, và danh mục không
sống trong tệp này.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.contracts.errors import ConfigError
from app.contracts.types import EvidenceTier, Finding, GateName, GateVerdict

if TYPE_CHECKING:
    from app.gates.registry import GateContext

_OP_KEY = "design.compare_op"

_COVERED = "covered"
_NA_TOKEN = "n/a"


class QualityCell(BaseModel):
    """Một ô của ma trận: một quyết định trên một đặc tính chất lượng."""

    characteristic: str
    file: str
    line: int
    decision: str | None = None


class DesignMatrix(BaseModel):
    """Ma trận phủ đã nạp, kèm neo về tệp gốc.

    `source_file`/`source_line` tồn tại để những phát hiện KHÔNG thuộc về một ô
    cụ thể (đường bắt buộc bị thiếu hẳn) vẫn neo được vào một chỗ có thật. Một
    phát hiện dạng "thứ này vắng mặt" là dạng khó neo nhất, và cũng là dạng
    quan trọng nhất: nó không phải luật bị vi phạm, nó là luật không được gọi.
    """

    risk_band: str
    source_file: str
    source_line: int
    cells: list[QualityCell] = Field(default_factory=list)
    path_decisions: dict[str, str] = Field(default_factory=dict)


def _is_na(decision: str) -> bool:
    return decision.strip().lower().startswith(_NA_TOKEN)


def check_design(ctx: GateContext) -> GateVerdict:
    """Chấm cổng `design`."""
    if ctx.design_matrix is None:
        return ctx.refuse(
            GateName.DESIGN, "không có ma trận phủ nào được truyền vào", _OP_KEY
        )

    matrix = ctx.design_matrix
    floor = ctx.require(f"design.risk_floors.{matrix.risk_band}")
    silent_na = ctx.require("design.silent_na")
    na_policy = ctx.require("design.na_policy")
    na_prefix = ctx.require("design.na_reason_prefix")
    required_paths = list(ctx.require("design.required_paths"))

    if silent_na not in ("reject", "allow"):
        raise ConfigError("design.silent_na", f"giá trị lạ: {silent_na!r}")
    if na_policy not in ("require_reason", "allow_silent"):
        raise ConfigError("design.na_policy", f"giá trị lạ: {na_policy!r}")

    if not matrix.cells:
        return ctx.refuse(
            GateName.DESIGN,
            "ma trận không có ô nào — mẫu số rỗng là ĐỎ, không phải xanh",
            _OP_KEY,
        )

    findings: list[Finding] = []
    covered: set[str] = set()

    for cell in matrix.cells:
        decision = (cell.decision or "").strip()

        if not decision:
            if silent_na == "reject":
                findings.append(
                    Finding(
                        rule_id="DES-SILENT-NA",
                        severity="error",
                        file=cell.file,
                        line=cell.line,
                        finding=(
                            f"ô {cell.characteristic!r} không có quyết định nào — "
                            f"đây là defect, không phải 'đã phủ'"
                        ),
                    )
                )
            continue

        if _is_na(decision):
            reason = decision[len(_NA_TOKEN) :].lstrip(" :–-").strip()
            if reason.lower().startswith("because"):
                reason = reason[len("because") :].strip()
            if na_policy == "require_reason" and not reason:
                findings.append(
                    Finding(
                        rule_id="DES-NA-NO-REASON",
                        severity="error",
                        file=cell.file,
                        line=cell.line,
                        finding=(
                            f"ô {cell.characteristic!r} khai N/A không kèm lý do, trong khi "
                            f"danh mục này khai na_policy=require_reason"
                        ),
                    )
                )
            continue

        if decision.lower() == _COVERED:
            covered.add(cell.characteristic)

    for path in required_paths:
        if path not in matrix.path_decisions:
            findings.append(
                Finding(
                    rule_id="DES-PATH-MISSING",
                    severity="error",
                    file=matrix.source_file,
                    line=matrix.source_line,
                    finding=(
                        f"đường bắt buộc {path!r} vắng khỏi ma trận — "
                        f"đường vắng mặt không tạo ra ô trống nào để luật bắt"
                    ),
                )
            )
            continue

        value = (matrix.path_decisions[path] or "").strip()
        if not value:
            findings.append(
                Finding(
                    rule_id="DES-PATH-MISSING",
                    severity="error",
                    file=matrix.source_file,
                    line=matrix.source_line,
                    finding=f"đường bắt buộc {path!r} có mặt nhưng không có quyết định",
                )
            )
            continue

        if _is_na(value):
            if not value.startswith(na_prefix) or not value[len(na_prefix) :].strip():
                findings.append(
                    Finding(
                        rule_id="DES-PATH-NA-NO-REASON",
                        severity="error",
                        file=matrix.source_file,
                        line=matrix.source_line,
                        finding=(
                            f"đường {path!r} khai N/A mà không đúng khuôn "
                            f"{na_prefix!r}<lý do> — im lặng ở đây là vi phạm"
                        ),
                    )
                )

    measured = len(covered)
    floor_ok, op = ctx.compare_by(measured, floor, _OP_KEY)
    if not floor_ok:
        findings.append(
            Finding(
                rule_id="DES-FLOOR",
                severity="error",
                file=matrix.source_file,
                line=matrix.source_line,
                finding=(
                    f"phủ {measured} đặc tính, sàn cho band {matrix.risk_band!r} đòi "
                    f"{op} {floor}"
                ),
            )
        )

    has_error = any(f.severity == "error" for f in findings)
    ok = floor_ok and not has_error

    return GateVerdict(
        gate=GateName.DESIGN,
        verdict="pass" if ok else "fail",
        evidence_tier=EvidenceTier.RETRIEVED,
        findings=findings,
        compare_op=op,
        denominator=len(matrix.cells) + len(required_paths),
        blocked=not ok,
        reason=(
            f"covered={measured} {op} floor={floor} ({matrix.risk_band}); "
            f"{len(findings)} phát hiện trên {len(matrix.cells)} ô + "
            f"{len(required_paths)} đường bắt buộc"
        ),
    )
