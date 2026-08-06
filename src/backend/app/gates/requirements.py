"""Gate 1 — tiêu chí nghiệm thu có kiểm được bằng máy không.

Gate này KHÔNG chấm chất lượng của tiêu chí; nó chấm TÍNH KIỂM ĐƯỢC. Lý do:
không có oracle thì không cưỡng chế được, chỉ nhắc được — và một tiêu chí không
kiểm được bằng máy làm mù toàn bộ mắt xích phía sau, vì gate `execution` sau này
đối chiếu diff với chính những tiêu chí này.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.contracts.types import EvidenceTier, Finding, GateName, GateVerdict

if TYPE_CHECKING:  # tránh vòng import: registry → gate, không có chiều ngược
    from app.gates.registry import GateContext

_OP_KEY = "requirements.compare_op"


class AcceptanceCriterion(BaseModel):
    """Một tiêu chí nghiệm thu trích từ front-matter của kế hoạch.

    `file`/`line` là bắt buộc vì mọi `Finding` sinh ra từ đây phải neo được về
    đúng dòng trong tệp kế hoạch; một phát hiện không neo được thì downstream
    coi như không tồn tại.
    """

    id: str
    file: str
    line: int
    verification_type: str
    binary_check: bool | None = None
    rules: list[dict[str, Any]] = Field(default_factory=list)
    manual_checker: str | None = None


def check_requirements(ctx: GateContext) -> GateVerdict:
    """Chấm cổng `requirements`."""
    if ctx.criteria is None:
        return ctx.refuse(
            GateName.REQUIREMENTS,
            "không có tạo tác tiêu chí nghiệm thu nào được truyền vào",
            _OP_KEY,
        )

    allowed_types = list(ctx.require("requirements.verification_types"))
    rule_fields = list(ctx.require("requirements.rule_required_fields"))
    max_violations = ctx.require("requirements.max_violations")

    denominator = len(ctx.criteria)
    if denominator == 0:
        return ctx.refuse(
            GateName.REQUIREMENTS,
            "kế hoạch không có tiêu chí nghiệm thu nào — chưa soi, không phải đã sạch",
            _OP_KEY,
        )

    findings: list[Finding] = []
    violating: set[str] = set()

    for crit in ctx.criteria:
        before = len(findings)
        vtype = crit.verification_type

        if vtype not in allowed_types:
            findings.append(
                Finding(
                    rule_id="REQ-VTYPE-UNKNOWN",
                    severity="error",
                    file=crit.file,
                    line=crit.line,
                    finding=(
                        f"tiêu chí {crit.id!r} khai verification_type={vtype!r}, "
                        f"không thuộc {allowed_types} — không có oracle bằng máy"
                    ),
                )
            )
        elif vtype == "test":
            if crit.binary_check is not True:
                findings.append(
                    Finding(
                        rule_id="REQ-TEST-NO-BINARY",
                        severity="error",
                        file=crit.file,
                        line=crit.line,
                        finding=(
                            f"tiêu chí {crit.id!r} nhánh test thiếu binary_check=true — "
                            f"không có mã thoát thì không có phán quyết"
                        ),
                    )
                )
        elif vtype == "rule":
            if not crit.rules:
                findings.append(
                    Finding(
                        rule_id="REQ-RULE-NO-RULES",
                        severity="error",
                        file=crit.file,
                        line=crit.line,
                        finding=(
                            f"tiêu chí {crit.id!r} nhánh rule không khai rules[] — "
                            f"luật tồn tại nhưng máy dò thì không"
                        ),
                    )
                )
            else:
                for idx, rule in enumerate(crit.rules):
                    missing = [
                        f
                        for f in rule_fields
                        if f not in rule or not str(rule[f] if rule[f] is not None else "").strip()
                    ]
                    if missing:
                        findings.append(
                            Finding(
                                rule_id="REQ-RULE-FIELD-MISSING",
                                severity="error",
                                file=crit.file,
                                line=crit.line,
                                finding=(
                                    f"tiêu chí {crit.id!r} rules[{idx}] thiếu trường "
                                    f"{missing} trong {rule_fields}"
                                ),
                            )
                        )
        elif vtype == "manual":
            if not (crit.manual_checker or "").strip():
                findings.append(
                    Finding(
                        rule_id="REQ-MANUAL-NO-CHECKER",
                        severity="error",
                        file=crit.file,
                        line=crit.line,
                        finding=(
                            f"tiêu chí {crit.id!r} nhánh manual không nêu tên người kiểm — "
                            f"không ai chịu trách nhiệm thì không ai kiểm"
                        ),
                    )
                )

        if len(findings) > before:
            violating.add(crit.id)

    measured = len(violating)
    ok, op = ctx.compare_by(measured, max_violations, _OP_KEY)

    return GateVerdict(
        gate=GateName.REQUIREMENTS,
        verdict="pass" if ok else "fail",
        evidence_tier=EvidenceTier.RETRIEVED,
        findings=findings,
        compare_op=op,
        denominator=denominator,
        blocked=not ok,
        reason=(
            f"{measured}/{denominator} tiêu chí không kiểm được bằng máy "
            f"(ngưỡng {op} {max_violations})"
        ),
    )
