"""Gate 3 — quét luật tất định trên PR diff, khớp ma trận hàng-đối-hàng.

Hai phép kiểm chạy trên cùng một lần parse diff:

1. Bộ luật tất định. Mỗi luật BẮT BUỘC có máy dò (`pattern`); một luật không có
   máy dò là một lời khuyên, và 143/145 luật của hệ tham chiếu ở đúng trạng thái
   đó. Ở đây `pattern` rỗng ⇒ dừng và nêu tên khoá, không hạ cấp thành advisory.
2. Khớp hàng-đối-hàng. Một tệp bị đổi mà không ánh xạ về hàng ma trận nào là ca
   nguy hiểm nhất: đó không phải luật bị vi phạm, đó là luật không được gọi tới.

Giới hạn khai thẳng: bộ quét này là regex trên văn bản diff, nên nó trả tập NHỎ
HƠN thật — đã đo được cùng một bài học ba lần. Vì vậy `evidence_tier` là
`derived`, không phải `executed`, và việc nâng lên AST nằm trong vế "điều kiện
xem lại" của `config/gates.yaml`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.contracts.errors import ConfigError, EmptyBlockingSetError
from app.contracts.types import EvidenceTier, Finding, GateName, GateVerdict

if TYPE_CHECKING:
    from app.gates.registry import GateContext

_OP_KEY = "execution.compare_op"
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_VALID_SEVERITIES = ("info", "warn", "error")


class ExecutionInput(BaseModel):
    """PR diff cộng phần ma trận đã được duyệt ở gate 2."""

    diff: str
    approved_rows: list[str] = Field(default_factory=list)
    file_row_map: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class AddedLine:
    """Một dòng THÊM MỚI của diff, đã biết mình thuộc tệp nào, dòng bao nhiêu."""

    file: str
    line: int
    text: str


@dataclass(frozen=True)
class CompiledRule:
    rule_id: str
    severity: str
    message: str
    pattern: re.Pattern[str]


def parse_added_lines(diff: str) -> tuple[list[AddedLine], list[str]]:
    """Tách các dòng thêm mới, kèm danh sách tệp bị đụng tới.

    Trả cả danh sách tệp vì một tệp có thể chỉ bị XOÁ dòng — nó vẫn là một tệp
    bị đổi và vẫn phải khớp một hàng ma trận, dù nó không góp dòng nào vào mẫu
    số quét luật.
    """
    added: list[AddedLine] = []
    files: list[str] = []
    current: str | None = None
    lineno = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target in ("/dev/null", ""):
                current = None
                continue
            current = target[2:] if target[:2] in ("a/", "b/") else target
            if current not in files:
                files.append(current)
            lineno = 0
            continue
        if raw.startswith("--- "):
            continue
        hunk = _HUNK.match(raw)
        if hunk:
            lineno = int(hunk.group(1))
            continue
        if current is None or lineno == 0:
            continue
        if raw.startswith("+"):
            added.append(AddedLine(file=current, line=lineno, text=raw[1:]))
            lineno += 1
        elif raw.startswith("-"):
            continue
        elif raw.startswith(" ") or raw == "":
            lineno += 1

    return added, files


def _compile_rules(raw_rules: Any) -> list[CompiledRule]:
    """Dựng bộ luật, từ chối mọi luật không có máy dò."""
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ConfigError("execution.rules", "bộ luật rỗng — không có gì để cưỡng chế")

    compiled: list[CompiledRule] = []
    for idx, rule in enumerate(raw_rules):
        if not isinstance(rule, dict):
            raise ConfigError(f"execution.rules[{idx}]", "luật không phải ánh xạ")

        rule_id = str(rule["id"]).strip() if "id" in rule and rule["id"] else ""
        if not rule_id:
            raise ConfigError(f"execution.rules[{idx}].id", "luật không có định danh")

        if "severity" not in rule or rule["severity"] not in _VALID_SEVERITIES:
            raise ConfigError(
                f"execution.rules[{rule_id}].severity",
                f"phải thuộc {list(_VALID_SEVERITIES)}",
            )

        pattern = str(rule["pattern"]).strip() if "pattern" in rule and rule["pattern"] else ""
        if not pattern:
            raise ConfigError(
                f"execution.rules[{rule_id}].pattern",
                "luật không có máy dò — luật tồn tại mà máy dò thì không là fail-open",
            )
        try:
            compiled_pattern = re.compile(pattern)
        except re.error as exc:
            raise ConfigError(
                f"execution.rules[{rule_id}].pattern", f"regex không hợp lệ: {exc}"
            ) from exc

        message = str(rule["message"]).strip() if "message" in rule and rule["message"] else ""
        if not message:
            raise ConfigError(f"execution.rules[{rule_id}].message", "luật không có diễn giải")

        compiled.append(
            CompiledRule(
                rule_id=rule_id,
                severity=rule["severity"],
                message=message,
                pattern=compiled_pattern,
            )
        )
    return compiled


def check_execution(ctx: GateContext) -> GateVerdict:
    """Chấm cổng `execution`."""
    if ctx.execution is None:
        return ctx.refuse(GateName.EXECUTION, "không có PR diff nào được truyền vào", _OP_KEY)

    rules = _compile_rules(ctx.require("execution.rules"))
    blocking_severities = list(ctx.require("execution.blocking_severities"))
    max_violations = ctx.require("execution.max_violations")

    if not any(rule.severity in blocking_severities for rule in rules):
        raise EmptyBlockingSetError(
            "không luật execution nào mang severity thuộc "
            f"{blocking_severities} — bộ luật chỉ khuyến nghị, không cưỡng chế được"
        )

    added, changed_files = parse_added_lines(ctx.execution.diff)
    denominator = len(added)
    if denominator == 0:
        return ctx.refuse(
            GateName.EXECUTION,
            "diff không có dòng thêm mới nào để quét — '0 vi phạm' ở đây không "
            "phân biệt được với 'chưa quét gì'",
            _OP_KEY,
        )

    findings: list[Finding] = []

    for line in added:
        for rule in rules:
            if rule.pattern.search(line.text):
                findings.append(
                    Finding(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        file=line.file,
                        line=line.line,
                        finding=f"{rule.message} | {line.text.strip()}",
                    )
                )

    first_line: dict[str, int] = {}
    for line in added:
        if line.file not in first_line:
            first_line[line.file] = line.line

    approved = set(ctx.execution.approved_rows)
    for path in changed_files:
        anchor = first_line[path] if path in first_line else 1
        if path not in ctx.execution.file_row_map:
            findings.append(
                Finding(
                    rule_id="EXE-ROW-MISSING",
                    severity="error",
                    file=path,
                    line=anchor,
                    finding=(
                        f"tệp {path!r} bị đổi nhưng không ánh xạ về hàng ma trận nào — "
                        f"không có hàng thì không có ô trống để luật bắt"
                    ),
                )
            )
            continue
        row = ctx.execution.file_row_map[path]
        if row not in approved:
            findings.append(
                Finding(
                    rule_id="EXE-ROW-UNAPPROVED",
                    severity="error",
                    file=path,
                    line=anchor,
                    finding=(
                        f"tệp {path!r} khai thuộc hàng {row!r}, hàng này không nằm trong "
                        f"ma trận đã duyệt ở gate design"
                    ),
                )
            )

    measured = sum(1 for f in findings if f.severity in blocking_severities)
    ok, op = ctx.compare_by(measured, max_violations, _OP_KEY)

    return GateVerdict(
        gate=GateName.EXECUTION,
        verdict="pass" if ok else "fail",
        evidence_tier=EvidenceTier.DERIVED,
        findings=findings,
        compare_op=op,
        denominator=denominator,
        blocked=not ok,
        reason=(
            f"{measured} vi phạm chặn (ngưỡng {op} {max_violations}) trên {denominator} "
            f"dòng thêm mới, {len(changed_files)} tệp"
        ),
    )
