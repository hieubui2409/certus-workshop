"""Gate 5 — cửa sổ 24h / 7d / 30d sau khi ship.

Đây là chỗ luật ghép của note 04 §3 (nối 3) được thi hành:

    Gate so `threshold` với `wilson_lower_bound(k, n)`, KHÔNG BAO GIỜ với `k/n`.
    Và gate phải in ra `n`. `n` không đủ để đạt threshold ở mọi kịch bản ⇒
    verdict là UNVERIFIED, không phải pass.

Vì sao điều đó không phải chi tiết kỹ thuật: một bản ghi `{killed: 2,
survived: 0}` cho point estimate `0.0` và PASS, trong khi khoảng Wilson95 của
`0/2` là `[0.0000, 0.6576]` — tỉ lệ thật có thể tới 65,8%. Point estimate cho
PASS, interval cho FAIL, và cái thứ hai đúng.

`GateVerdict` chỉ có hệ {pass, fail}, nên trạng thái "chưa đo đủ để kết luận"
được phát ra dưới dạng `verdict="fail"` kèm `reason` mở đầu bằng `UNVERIFIED:`
và `evidence_tier=None`. Nó là một phán quyết hợp lệ, và nó KHÔNG được đọc
thành "không có sự cố".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.contracts.types import EvidenceTier, Finding, GateName, GateVerdict

if TYPE_CHECKING:
    from app.gates.registry import GateContext

_OP_KEY = "outcome.compare_op"


class OutcomeWindow(BaseModel):
    """Quan sát sau ship trên một cửa sổ thời gian.

    `k` là số sự cố, `n` là số quan sát độc lập — đếm ĐƠN VỊ ĐỘC LẬP, không đếm
    dòng log. Hai con số này luôn đi cùng nhau; báo `k` mà không báo `n` là kiểu
    báo cáo mà cả ba tài liệu nền đều cấm.
    """

    label: str
    k: int
    n: int
    file: str
    line: int


def check_outcome(ctx: GateContext) -> GateVerdict:
    """Chấm cổng `outcome`."""
    if ctx.outcome_windows is None:
        return ctx.refuse(
            GateName.OUTCOME, "không có quan sát sau ship nào được truyền vào", _OP_KEY
        )

    windows = list(ctx.require("outcome.windows"))
    max_rate = ctx.require("outcome.max_incident_rate")
    conf = ctx.require("outcome.conf")

    samples = list(ctx.outcome_windows)
    if not samples:
        return ctx.refuse(
            GateName.OUTCOME,
            "chưa có quan sát nào sau ship — mẫu số rỗng là ĐỎ, không phải xanh",
            _OP_KEY,
        )

    anchor = samples[0]
    by_label = {s.label: s for s in samples}
    findings: list[Finding] = []
    lowers: list[float] = []
    unverified = False

    for label in windows:
        if label not in by_label:
            unverified = True
            findings.append(
                Finding(
                    rule_id="OUT-WINDOW-MISSING",
                    severity="error",
                    file=anchor.file,
                    line=anchor.line,
                    finding=f"cửa sổ {label!r} không có quan sát nào — chưa đo, không phải sạch",
                )
            )
            continue

        sample = by_label[label]
        min_n = ctx.require(f"outcome.min_n.{label}")

        if sample.n < min_n:
            unverified = True
            findings.append(
                Finding(
                    rule_id="OUT-N-TOO-SMALL",
                    severity="error",
                    file=sample.file,
                    line=sample.line,
                    finding=(
                        f"cửa sổ {label!r} có n={sample.n} < min_n={min_n}: cỡ mẫu này "
                        f"không đủ để biên dưới Wilson nằm đúng phía ngưỡng ở bất kỳ kịch bản nào"
                    ),
                )
            )
            continue

        lower = ctx.wilson_lower(sample.k, sample.n, conf)
        lowers.append(lower)
        window_ok, op = ctx.compare_by(lower, max_rate, _OP_KEY)
        if not window_ok:
            findings.append(
                Finding(
                    rule_id="OUT-RATE-EXCEEDS",
                    severity="error",
                    file=sample.file,
                    line=sample.line,
                    finding=(
                        f"cửa sổ {label!r}: k={sample.k}, n={sample.n}, biên dưới Wilson"
                        f"({conf})={lower:.4f}, trần đòi {op} {max_rate}"
                    ),
                )
            )

    measured = max(lowers) if lowers else 0.0
    rate_ok, op = ctx.compare_by(measured, max_rate, _OP_KEY)
    ok = rate_ok and not unverified and not any(f.severity == "error" for f in findings)

    denominator = sum(s.n for s in samples)
    reason = (
        f"UNVERIFIED: cỡ mẫu chưa đủ trên ít nhất một cửa sổ; "
        f"n theo cửa sổ = { {s.label: s.n for s in samples} }"
        if unverified
        else (
            f"biên dưới Wilson tệ nhất={measured:.4f} {op} {max_rate}; "
            f"n theo cửa sổ = { {s.label: s.n for s in samples} }"
        )
    )

    return GateVerdict(
        gate=GateName.OUTCOME,
        verdict="pass" if ok else "fail",
        evidence_tier=None if unverified else EvidenceTier.DERIVED,
        findings=findings,
        compare_op=op,
        denominator=denominator,
        blocked=not ok,
        reason=reason,
    )
