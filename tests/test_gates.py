"""Bộ kiểm của 5 gate.

Xương sống của tệp này là định nghĩa ĐO ĐƯỢC của "gate thật" (note 03 §1.4,
điều 1): mỗi gate phải có **ba ca đi qua cùng một đường mã** — vi phạm ⇒ `fail`,
không vi phạm ⇒ `pass`, và ca **BIÊN** (số đo bằng đúng ngưỡng) cho kết quả do
khoá `compare_op` quyết định.

Cách kiểm ca biên ở đây mạnh hơn "assert một giá trị": cùng một input biên được
chạy **hai lần**, chỉ đổi `compare_op` trong config. Verdict phải ĐẢO. Nếu không
đảo thì khoá config không được đọc — và đó chính là anti-pattern `E4` (*"thiếu
ca biên, dấu so sánh để ngầm"*), thứ mà một assert đơn lẻ không bao giờ bắt được.
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts.errors import ConfigError, EmptyBlockingSetError  # noqa: E402
from app.contracts.types import GateName  # noqa: E402
from app.gates.design import DesignMatrix, QualityCell  # noqa: E402
from app.gates.execution import ExecutionInput, parse_added_lines  # noqa: E402
from app.gates.outcome import OutcomeWindow  # noqa: E402
from app.gates.registry import (  # noqa: E402
    GateContext,
    load_gates_config,
    run_chain,
    run_gate,
    wilson_lower_bound,
)
from app.gates.requirements import AcceptanceCriterion  # noqa: E402


# ───────────────────────── hạ tầng kiểm ─────────────────────────


def reference_wilson_lower(k: int, n: int, conf: float = 0.95) -> float:
    """Oracle độc lập cho biên dưới Wilson.

    Cố ý viết lại công thức ở đây thay vì gọi `core.stats`: một bộ kiểm dùng
    chính implementation nó đi kiểm thì nó chỉ chứng minh rằng hàm đó bằng chính
    nó. Neo hồi quy của tài liệu nền — `wilson(8, 10) == (0.490162, 0.943318)` —
    được ghim trong `test_reference_oracle_matches_regression_anchor`.
    """
    if n == 0:
        return 0.0
    if k == 0:
        # Ép cứng thay vì để sai số dấu phẩy động trả về ~1e-17. Biên là chỗ hay
        # sai nhất nên nó phải so được bằng `==`, không phải bằng dung sai.
        return 0.0
    z = 1.959963984540054 if abs(conf - 0.95) < 1e-9 else _z_for(conf)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half)


def _z_for(conf: float) -> float:
    from statistics import NormalDist

    return NormalDist().inv_cdf(1 - (1 - conf) / 2)


def make_ctx(config: dict[str, Any] | None = None, **artifacts: Any) -> GateContext:
    return GateContext(
        config=load_gates_config() if config is None else config,
        wilson_lower=reference_wilson_lower,
        **artifacts,
    )


def with_op(gate_key: str, op: str) -> dict[str, Any]:
    """Bản sao config chỉ khác đúng một khoá `compare_op`."""
    cfg = copy.deepcopy(load_gates_config())
    cfg[gate_key]["compare_op"] = op
    return cfg


def drop_key(dotted: str) -> dict[str, Any]:
    """Bản sao config đã xoá đúng một khoá — dùng để kiểm fail-closed."""
    cfg = copy.deepcopy(load_gates_config())
    node: Any = cfg
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[part]
    del node[parts[-1]]
    return cfg


def test_reference_oracle_matches_regression_anchor() -> None:
    """Đối chứng cho chính oracle của bộ kiểm.

    Không có bước này thì mọi khẳng định về Wilson phía dưới chỉ chứng minh rằng
    một hàm sai bằng chính nó. Neo lấy từ note 04 §3.
    """
    assert reference_wilson_lower(8, 10) == pytest.approx(0.490162, abs=5e-7)
    assert reference_wilson_lower(2, 2) == pytest.approx(0.3424, abs=5e-5)
    assert reference_wilson_lower(3, 3) == pytest.approx(0.4385, abs=5e-5)
    assert reference_wilson_lower(0, 2) == 0.0


def test_registry_wilson_resolver_agrees_with_the_oracle() -> None:
    """Mối nối thật tới `app.core.stats.intervals` phải trùng oracle."""
    for k, n in ((8, 10), (2, 2), (3, 3), (0, 2), (7, 40)):
        assert wilson_lower_bound(k, n, 0.95) == pytest.approx(
            reference_wilson_lower(k, n, 0.95), abs=1e-9
        )


# ───────────────────────── gate 1: requirements ─────────────────────────


def _crit(**kw: Any) -> AcceptanceCriterion:
    base: dict[str, Any] = {"id": "AC-1", "file": "plan.md", "line": 10}
    base.update(kw)
    return AcceptanceCriterion(**base)


CLEAN_CRITERIA = [
    _crit(id="AC-1", verification_type="test", binary_check=True),
    _crit(
        id="AC-2",
        verification_type="rule",
        rules=[{"scope": "src/**", "match": "eval(", "assert": "absent", "severity": "error"}],
    ),
    _crit(id="AC-3", verification_type="manual", manual_checker="Trần Thu Hà"),
]


def test_requirements_violating_case_fails() -> None:
    ctx = make_ctx(criteria=[_crit(verification_type="vibes")])
    verdict = run_gate(GateName.REQUIREMENTS, ctx)

    assert verdict.verdict == "fail"
    assert verdict.blocked is True
    assert verdict.denominator == 1
    assert [f.rule_id for f in verdict.findings] == ["REQ-VTYPE-UNKNOWN"]


def test_requirements_clean_case_passes() -> None:
    verdict = run_gate(GateName.REQUIREMENTS, make_ctx(criteria=CLEAN_CRITERIA))

    assert verdict.verdict == "pass"
    assert verdict.blocked is False
    assert verdict.denominator == 3
    assert verdict.findings == []


def test_requirements_boundary_case_is_decided_by_compare_op() -> None:
    """Ca BIÊN: số vi phạm == `max_violations` (0). Dấu so sánh quyết định."""
    ctx_le = make_ctx(with_op("requirements", "<="), criteria=CLEAN_CRITERIA)
    ctx_lt = make_ctx(with_op("requirements", "<"), criteria=CLEAN_CRITERIA)

    verdict_le = run_gate(GateName.REQUIREMENTS, ctx_le)
    verdict_lt = run_gate(GateName.REQUIREMENTS, ctx_lt)

    assert verdict_le.verdict == "pass"
    assert verdict_le.compare_op == "<="
    assert verdict_lt.verdict == "fail"
    assert verdict_lt.compare_op == "<"


@pytest.mark.parametrize(
    ("criterion", "rule_id"),
    [
        (_crit(verification_type="test", binary_check=None), "REQ-TEST-NO-BINARY"),
        (_crit(verification_type="test", binary_check=False), "REQ-TEST-NO-BINARY"),
        (_crit(verification_type="rule", rules=[]), "REQ-RULE-NO-RULES"),
        (
            _crit(verification_type="rule", rules=[{"scope": "src", "match": "x"}]),
            "REQ-RULE-FIELD-MISSING",
        ),
        (
            _crit(
                verification_type="rule",
                rules=[{"scope": "src", "match": "x", "assert": "", "severity": "error"}],
            ),
            "REQ-RULE-FIELD-MISSING",
        ),
        (_crit(verification_type="manual", manual_checker=None), "REQ-MANUAL-NO-CHECKER"),
        (_crit(verification_type="manual", manual_checker="   "), "REQ-MANUAL-NO-CHECKER"),
    ],
)
def test_requirements_each_documented_fail_branch_is_reachable(
    criterion: AcceptanceCriterion, rule_id: str
) -> None:
    """Mỗi nhánh FAIL trên giấy phải có một đường mã thật dẫn tới nó.

    Hệ tham chiếu có chuỗi `'fail'` chỉ trong khai báo type và comment: tập
    verdict đến được có đúng một phần tử, và như thế thì nó không phải cổng, nó
    là một cái ống.
    """
    verdict = run_gate(GateName.REQUIREMENTS, make_ctx(criteria=[criterion]))
    assert verdict.verdict == "fail"
    assert rule_id in {f.rule_id for f in verdict.findings}


def test_requirements_missing_artifact_blocks_instead_of_skipping() -> None:
    verdict = run_gate(GateName.REQUIREMENTS, make_ctx(criteria=None))
    assert (verdict.verdict, verdict.blocked, verdict.denominator) == ("fail", True, 0)
    assert verdict.skipped is False


def test_requirements_empty_denominator_is_red() -> None:
    verdict = run_gate(GateName.REQUIREMENTS, make_ctx(criteria=[]))
    assert (verdict.verdict, verdict.blocked, verdict.denominator) == ("fail", True, 0)


# ───────────────────────── gate 2: design ─────────────────────────

_CHARACTERISTICS = [
    "functional_suitability",
    "performance_efficiency",
    "compatibility",
    "usability",
    "reliability",
    "security",
    "maintainability",
    "portability",
]

REQUIRED_PATHS = list(load_gates_config()["design"]["required_paths"])


def make_matrix(
    covered: int,
    *,
    risk_band: str = "high",
    extra_cells: list[QualityCell] | None = None,
    paths: dict[str, str] | None = None,
) -> DesignMatrix:
    cells = [
        QualityCell(characteristic=name, decision="covered", file="matrix.yaml", line=idx + 2)
        for idx, name in enumerate(_CHARACTERISTICS[:covered])
    ]
    cells.extend(extra_cells or [])
    return DesignMatrix(
        risk_band=risk_band,
        source_file="matrix.yaml",
        source_line=1,
        cells=cells,
        path_decisions=paths if paths is not None else {p: "tests/test_x.py::test_y" for p in REQUIRED_PATHS},
    )


def test_design_violating_case_fails_on_floor() -> None:
    verdict = run_gate(GateName.DESIGN, make_ctx(design_matrix=make_matrix(5)))
    assert verdict.verdict == "fail"
    assert "DES-FLOOR" in {f.rule_id for f in verdict.findings}


def test_design_clean_case_passes() -> None:
    verdict = run_gate(GateName.DESIGN, make_ctx(design_matrix=make_matrix(7)))
    assert verdict.verdict == "pass"
    assert verdict.findings == []
    assert verdict.denominator == 7 + len(REQUIRED_PATHS)


def test_design_boundary_case_is_decided_by_compare_op() -> None:
    """Ca BIÊN: covered == floor (band `high` ⇒ 6)."""
    matrix = make_matrix(6)
    verdict_ge = run_gate(GateName.DESIGN, make_ctx(with_op("design", ">="), design_matrix=matrix))
    verdict_gt = run_gate(GateName.DESIGN, make_ctx(with_op("design", ">"), design_matrix=matrix))

    assert (verdict_ge.verdict, verdict_ge.compare_op) == ("pass", ">=")
    assert (verdict_gt.verdict, verdict_gt.compare_op) == ("fail", ">")


def test_design_silent_na_policy_is_actually_read() -> None:
    """Chạy hai lần trên CÙNG một ô, chỉ đổi `silent_na`.

    Hai phán quyết khác nhau ⇒ XANH; giống nhau ⇒ ĐỎ (note 03 §4.3). Đây là phép
    kiểm phân biệt "chính sách được đọc" với "chính sách được khai".
    """
    matrix = make_matrix(
        6,
        extra_cells=[QualityCell(characteristic="ai_ethics", decision=None, file="m.yaml", line=9)],
    )
    cfg_reject = copy.deepcopy(load_gates_config())
    cfg_reject["design"]["silent_na"] = "reject"
    cfg_allow = copy.deepcopy(load_gates_config())
    cfg_allow["design"]["silent_na"] = "allow"

    rejected = run_gate(GateName.DESIGN, make_ctx(cfg_reject, design_matrix=matrix))
    allowed = run_gate(GateName.DESIGN, make_ctx(cfg_allow, design_matrix=matrix))

    assert rejected.verdict == "fail"
    assert "DES-SILENT-NA" in {f.rule_id for f in rejected.findings}
    assert allowed.verdict == "pass"
    assert rejected.verdict != allowed.verdict


def test_design_na_policy_is_actually_read() -> None:
    """Hai chuẩn quốc tế nói ngược nhau, nên khoá này PHẢI đổi được phán quyết."""
    matrix = make_matrix(
        6,
        extra_cells=[QualityCell(characteristic="ai_ethics", decision="N/A", file="m.yaml", line=9)],
    )
    cfg_strict = copy.deepcopy(load_gates_config())
    cfg_strict["design"]["na_policy"] = "require_reason"
    cfg_loose = copy.deepcopy(load_gates_config())
    cfg_loose["design"]["na_policy"] = "allow_silent"

    strict = run_gate(GateName.DESIGN, make_ctx(cfg_strict, design_matrix=matrix))
    loose = run_gate(GateName.DESIGN, make_ctx(cfg_loose, design_matrix=matrix))

    assert strict.verdict == "fail"
    assert "DES-NA-NO-REASON" in {f.rule_id for f in strict.findings}
    assert loose.verdict == "pass"


def test_design_na_with_reason_is_accepted_under_require_reason() -> None:
    matrix = make_matrix(
        6,
        extra_cells=[
            QualityCell(
                characteristic="ai_ethics",
                decision="N/A because sản phẩm không có mô hình sinh nội dung",
                file="m.yaml",
                line=9,
            )
        ],
    )
    assert run_gate(GateName.DESIGN, make_ctx(design_matrix=matrix)).verdict == "pass"


def test_design_missing_required_path_fails() -> None:
    paths = {p: "tests/test_x.py::test_y" for p in REQUIRED_PATHS if p != "accessibility"}
    verdict = run_gate(GateName.DESIGN, make_ctx(design_matrix=make_matrix(7, paths=paths)))

    assert verdict.verdict == "fail"
    missing = [f for f in verdict.findings if f.rule_id == "DES-PATH-MISSING"]
    assert len(missing) == 1
    assert "accessibility" in missing[0].finding


def test_design_silently_uncovered_path_is_rejected() -> None:
    """"Paths present but silently uncovered = matrix rejected at Design Gate"."""
    paths = {p: "tests/test_x.py::test_y" for p in REQUIRED_PATHS}
    paths["concurrency_and_ordering"] = "N/A"
    verdict = run_gate(GateName.DESIGN, make_ctx(design_matrix=make_matrix(7, paths=paths)))

    assert verdict.verdict == "fail"
    assert "DES-PATH-NA-NO-REASON" in {f.rule_id for f in verdict.findings}


def test_design_path_na_with_reason_passes() -> None:
    paths = {p: "tests/test_x.py::test_y" for p in REQUIRED_PATHS}
    paths["data_migration"] = "N/A because dịch vụ này không có schema bền vững"
    assert run_gate(GateName.DESIGN, make_ctx(design_matrix=make_matrix(7, paths=paths))).verdict == "pass"


def test_design_missing_artifact_and_empty_matrix_block() -> None:
    assert run_gate(GateName.DESIGN, make_ctx(design_matrix=None)).blocked is True
    empty = make_matrix(0)
    verdict = run_gate(GateName.DESIGN, make_ctx(design_matrix=empty))
    assert (verdict.verdict, verdict.denominator) == ("fail", 0)


def test_design_unknown_risk_band_names_the_missing_key() -> None:
    with pytest.raises(ConfigError) as exc:
        run_gate(GateName.DESIGN, make_ctx(design_matrix=make_matrix(7, risk_band="apocalyptic")))
    assert exc.value.key == "design.risk_floors.apocalyptic"


# ───────────────────────── gate 2a: grid ─────────────────────────


class FakeGridVerdict:
    """Đứng thay `GridReviewVerdict` của `core.grid` cho tới khi kiểu đó chốt."""

    def __init__(
        self,
        *,
        risk_band: str = "high",
        cells_total: int = 12,
        cells_scored: int = 12,
        blocking_zones: list[str] | None = None,
        min_per_zone: dict[str, Any] | None = None,
    ) -> None:
        self.risk_band = risk_band
        self.cells_total = cells_total
        self.cells_scored = cells_scored
        self.blocking_zones = ["zone:checkout"] if blocking_zones is None else blocking_zones
        self.min_per_zone = {"zone:checkout": 1.0} if min_per_zone is None else min_per_zone
        self.source_file = "grid.json"
        self.source_line = 1


def test_grid_violating_case_fails() -> None:
    verdict = run_gate(
        GateName.GRID,
        make_ctx(grid_verdict=FakeGridVerdict(min_per_zone={"zone:checkout": 0.6})),
    )
    assert verdict.verdict == "fail"
    assert "GRID-ZONE-BELOW-FLOOR" in {f.rule_id for f in verdict.findings}


def test_grid_clean_case_passes() -> None:
    verdict = run_gate(GateName.GRID, make_ctx(grid_verdict=FakeGridVerdict()))
    assert verdict.verdict == "pass"
    assert verdict.denominator == 12


def test_grid_boundary_case_is_decided_by_compare_op() -> None:
    """Ca BIÊN: điểm zone tệ nhất == `min_band_score` (1.0)."""
    grid = FakeGridVerdict(min_per_zone={"zone:checkout": 1.0})
    ge = run_gate(GateName.GRID, make_ctx(with_op("grid", ">="), grid_verdict=grid))
    gt = run_gate(GateName.GRID, make_ctx(with_op("grid", ">"), grid_verdict=grid))

    assert (ge.verdict, ge.compare_op) == ("pass", ">=")
    assert (gt.verdict, gt.compare_op) == ("fail", ">")


def test_grid_reads_the_rollup_summary_shape_too() -> None:
    """Chấp nhận đúng hình dạng `core.grid.rollup.min_per_zone()` trả về."""
    grid = FakeGridVerdict(
        min_per_zone={"zone:checkout": {"w": 0.9, "worst_band": "med", "worst_score": 0.6}}
    )
    verdict = run_gate(GateName.GRID, make_ctx(grid_verdict=grid))
    assert verdict.verdict == "fail"
    assert "GRID-ZONE-BELOW-FLOOR" in {f.rule_id for f in verdict.findings}


def test_grid_vanished_blocking_zone_is_red_not_ignored() -> None:
    """Zone chặn rời khỏi `min_per_zone` là ĐỎ — nó là con số vốn LÀ cái gate."""
    grid = FakeGridVerdict(
        blocking_zones=["zone:checkout", "zone:payment"],
        min_per_zone={"zone:checkout": 1.0},
    )
    verdict = run_gate(GateName.GRID, make_ctx(grid_verdict=grid))

    assert verdict.verdict == "fail"
    assert "GRID-ZONE-MISSING" in {f.rule_id for f in verdict.findings}


def test_grid_empty_blocking_set_is_a_block() -> None:
    """Bên bị chấm không được phép làm rỗng tập chặn."""
    verdict = run_gate(GateName.GRID, make_ctx(grid_verdict=FakeGridVerdict(blocking_zones=[])))
    assert (verdict.verdict, verdict.blocked) == ("fail", True)
    assert "GRID-EMPTY-BLOCKING-SET" in {f.rule_id for f in verdict.findings}


def test_grid_unreadable_zone_entry_refuses_to_guess() -> None:
    grid = FakeGridVerdict(min_per_zone={"zone:checkout": {"w": 0.9}})
    verdict = run_gate(GateName.GRID, make_ctx(grid_verdict=grid))
    assert "GRID-ZONE-UNREADABLE" in {f.rule_id for f in verdict.findings}


def test_grid_skips_only_on_declared_bands() -> None:
    low = run_gate(GateName.GRID, make_ctx(grid_verdict=FakeGridVerdict(risk_band="low")))
    assert (low.verdict, low.skipped) == ("pass", True)
    assert low.reason

    med = run_gate(GateName.GRID, make_ctx(grid_verdict=FakeGridVerdict(risk_band="medium")))
    assert med.skipped is False


def test_grid_missing_artifact_or_fields_blocks() -> None:
    assert run_gate(GateName.GRID, make_ctx(grid_verdict=None)).blocked is True

    class Truncated:
        risk_band = "high"
        cells_total = 4

    verdict = run_gate(GateName.GRID, make_ctx(grid_verdict=Truncated()))
    assert (verdict.verdict, verdict.blocked, verdict.denominator) == ("fail", True, 0)


def test_grid_zero_scored_cells_is_red() -> None:
    grid = FakeGridVerdict(cells_scored=0)
    verdict = run_gate(GateName.GRID, make_ctx(grid_verdict=grid))
    assert (verdict.verdict, verdict.denominator) == ("fail", 0)


# ───────────────────────── gate 3: execution ─────────────────────────

CLEAN_DIFF = """diff --git a/src/cart.py b/src/cart.py
--- a/src/cart.py
+++ b/src/cart.py
@@ -10,3 +10,5 @@
 def total(items):
+    if not items:
+        raise ValueError("giỏ rỗng")
     return sum(i.price for i in items)
"""

DIRTY_DIFF = """diff --git a/src/cart.py b/src/cart.py
--- a/src/cart.py
+++ b/src/cart.py
@@ -10,3 +10,4 @@
 def total(items):
+    return eval(items)
     return 0
"""


def exec_input(diff: str, **kw: Any) -> ExecutionInput:
    base: dict[str, Any] = {
        "diff": diff,
        "approved_rows": ["functional_suitability"],
        "file_row_map": {"src/cart.py": "functional_suitability"},
    }
    base.update(kw)
    return ExecutionInput(**base)


def test_execution_violating_case_fails_with_a_fully_anchored_finding() -> None:
    verdict = run_gate(GateName.EXECUTION, make_ctx(execution=exec_input(DIRTY_DIFF)))

    assert verdict.verdict == "fail"
    hit = next(f for f in verdict.findings if f.rule_id == "EXE-EVAL")
    assert (hit.file, hit.line, hit.severity) == ("src/cart.py", 11, "error")
    assert hit.finding.strip()


def test_execution_clean_case_passes() -> None:
    verdict = run_gate(GateName.EXECUTION, make_ctx(execution=exec_input(CLEAN_DIFF)))
    assert verdict.verdict == "pass"
    assert verdict.denominator == 2


def test_execution_boundary_case_is_decided_by_compare_op() -> None:
    """Ca BIÊN: 0 vi phạm chặn == `max_violations` (0)."""
    payload = exec_input(CLEAN_DIFF)
    le = run_gate(GateName.EXECUTION, make_ctx(with_op("execution", "<="), execution=payload))
    lt = run_gate(GateName.EXECUTION, make_ctx(with_op("execution", "<"), execution=payload))

    assert (le.verdict, le.compare_op) == ("pass", "<=")
    assert (lt.verdict, lt.compare_op) == ("fail", "<")


def test_execution_every_finding_carries_the_five_required_fields() -> None:
    verdict = run_gate(GateName.EXECUTION, make_ctx(execution=exec_input(DIRTY_DIFF)))
    assert verdict.findings
    for finding in verdict.findings:
        assert finding.rule_id.strip()
        assert finding.severity in ("info", "warn", "error")
        assert finding.file.strip()
        assert finding.line >= 1
        assert finding.finding.strip()


def test_execution_file_without_a_matrix_row_fails() -> None:
    """Không phải luật bị vi phạm — là luật KHÔNG ĐƯỢC GỌI TỚI."""
    verdict = run_gate(
        GateName.EXECUTION, make_ctx(execution=exec_input(CLEAN_DIFF, file_row_map={}))
    )
    assert verdict.verdict == "fail"
    assert "EXE-ROW-MISSING" in {f.rule_id for f in verdict.findings}


def test_execution_row_outside_the_approved_matrix_fails() -> None:
    verdict = run_gate(
        GateName.EXECUTION,
        make_ctx(execution=exec_input(CLEAN_DIFF, approved_rows=["security"])),
    )
    assert verdict.verdict == "fail"
    assert "EXE-ROW-UNAPPROVED" in {f.rule_id for f in verdict.findings}


def test_execution_empty_diff_is_red_not_clean() -> None:
    """"0 issues found" khi quét 0 dòng không phân biệt được với "chưa quét gì"."""
    verdict = run_gate(GateName.EXECUTION, make_ctx(execution=exec_input("")))
    assert (verdict.verdict, verdict.blocked, verdict.denominator) == ("fail", True, 0)


def test_execution_rule_without_a_detector_is_a_config_error() -> None:
    cfg = copy.deepcopy(load_gates_config())
    cfg["execution"]["rules"][0]["pattern"] = None
    with pytest.raises(ConfigError) as exc:
        run_gate(GateName.EXECUTION, make_ctx(cfg, execution=exec_input(CLEAN_DIFF)))
    assert exc.value.key == "execution.rules[EXE-EVAL].pattern"


def test_execution_advisory_only_ruleset_refuses_to_run() -> None:
    """Bộ luật không chặn được gì là lỗi cấu hình, không phải một kết quả tốt."""
    cfg = copy.deepcopy(load_gates_config())
    for rule in cfg["execution"]["rules"]:
        rule["severity"] = "info"
    with pytest.raises(EmptyBlockingSetError):
        run_gate(GateName.EXECUTION, make_ctx(cfg, execution=exec_input(CLEAN_DIFF)))


def test_execution_missing_artifact_blocks() -> None:
    assert run_gate(GateName.EXECUTION, make_ctx(execution=None)).blocked is True


def test_parse_added_lines_numbers_lines_against_the_new_file() -> None:
    added, files = parse_added_lines(CLEAN_DIFF)
    assert files == ["src/cart.py"]
    assert [(a.line, a.text.strip()) for a in added] == [
        (11, 'if not items:'),
        (12, 'raise ValueError("giỏ rỗng")'),
    ]


# ───────────────────────── gate 5: outcome ─────────────────────────


def windows(**overrides: tuple[int, int]) -> list[OutcomeWindow]:
    base = {"24h": (0, 40), "7d": (1, 40), "30d": (2, 80)}
    base.update(overrides)
    return [
        OutcomeWindow(label=label, k=k, n=n, file="outcomes.jsonl", line=idx + 1)
        for idx, (label, (k, n)) in enumerate(base.items())
    ]


def test_outcome_violating_case_fails() -> None:
    verdict = run_gate(GateName.OUTCOME, make_ctx(outcome_windows=windows(**{"7d": (20, 40)})))
    assert verdict.verdict == "fail"
    assert "OUT-RATE-EXCEEDS" in {f.rule_id for f in verdict.findings}


def test_outcome_clean_case_passes() -> None:
    verdict = run_gate(GateName.OUTCOME, make_ctx(outcome_windows=windows()))
    assert verdict.verdict == "pass"
    assert verdict.denominator == 160


def test_outcome_boundary_case_is_decided_by_compare_op() -> None:
    """Ca BIÊN: biên dưới Wilson bằng ĐÚNG `max_incident_rate`."""
    threshold = load_gates_config()["outcome"]["max_incident_rate"]
    exact = GateContext(
        config=with_op("outcome", "<="),
        wilson_lower=lambda k, n, conf: threshold,
        outcome_windows=windows(),
    )
    strict = GateContext(
        config=with_op("outcome", "<"),
        wilson_lower=lambda k, n, conf: threshold,
        outcome_windows=windows(),
    )

    assert (run_gate(GateName.OUTCOME, exact).verdict, exact.config["outcome"]["compare_op"]) == (
        "pass",
        "<=",
    )
    assert run_gate(GateName.OUTCOME, strict).verdict == "fail"


def test_outcome_small_sample_is_unverified_not_pass() -> None:
    """`n` không đủ ⇒ UNVERIFIED, và UNVERIFIED không được đọc thành 'sạch'."""
    verdict = run_gate(GateName.OUTCOME, make_ctx(outcome_windows=windows(**{"24h": (0, 3)})))

    assert verdict.verdict == "fail"
    assert verdict.evidence_tier is None
    assert verdict.reason is not None and verdict.reason.startswith("UNVERIFIED:")
    assert "OUT-N-TOO-SMALL" in {f.rule_id for f in verdict.findings}


def test_outcome_missing_window_fails() -> None:
    only_two = [w for w in windows() if w.label != "30d"]
    verdict = run_gate(GateName.OUTCOME, make_ctx(outcome_windows=only_two))
    assert verdict.verdict == "fail"
    assert "OUT-WINDOW-MISSING" in {f.rule_id for f in verdict.findings}


def test_outcome_reports_n_alongside_every_rate() -> None:
    """Dấu hiệu cargo cult #1: interval mà không bao giờ nói `n` từ đâu ra."""
    verdict = run_gate(GateName.OUTCOME, make_ctx(outcome_windows=windows(**{"7d": (20, 40)})))
    hit = next(f for f in verdict.findings if f.rule_id == "OUT-RATE-EXCEEDS")
    assert "n=40" in hit.finding and "k=20" in hit.finding
    assert verdict.reason is not None and "'7d': 40" in verdict.reason


def test_outcome_missing_or_empty_artifact_blocks() -> None:
    assert run_gate(GateName.OUTCOME, make_ctx(outcome_windows=None)).blocked is True
    verdict = run_gate(GateName.OUTCOME, make_ctx(outcome_windows=[]))
    assert (verdict.verdict, verdict.denominator) == ("fail", 0)


# ───────────────────────── fail-closed trên cấu hình ─────────────────────────

#: Tạo tác HỢP LỆ cho từng gate — để phép kiểm fail-closed chạy trên đường mã
#: đầy đủ, không phải trên nhánh thoát sớm.
_ARTIFACTS_FOR: dict[str, Any] = {
    "requirements": lambda: {"criteria": CLEAN_CRITERIA},
    "design": lambda: {"design_matrix": make_matrix(7)},
    "grid": lambda: {"grid_verdict": FakeGridVerdict()},
    "execution": lambda: {"execution": exec_input(CLEAN_DIFF)},
    "outcome": lambda: {"outcome_windows": windows()},
}


@pytest.mark.parametrize(
    ("dotted", "gate", "artifacts"),
    [
        ("requirements.verification_types", GateName.REQUIREMENTS, "requirements"),
        ("requirements.rule_required_fields", GateName.REQUIREMENTS, "requirements"),
        ("requirements.max_violations", GateName.REQUIREMENTS, "requirements"),
        ("requirements.compare_op", GateName.REQUIREMENTS, "requirements"),
        ("design.risk_floors", GateName.DESIGN, "design"),
        ("design.silent_na", GateName.DESIGN, "design"),
        ("design.na_policy", GateName.DESIGN, "design"),
        ("design.required_paths", GateName.DESIGN, "design"),
        ("design.compare_op", GateName.DESIGN, "design"),
        ("grid.min_band_score", GateName.GRID, "grid"),
        ("grid.skip_on_bands", GateName.GRID, "grid"),
        ("grid.compare_op", GateName.GRID, "grid"),
        ("execution.rules", GateName.EXECUTION, "execution"),
        ("execution.blocking_severities", GateName.EXECUTION, "execution"),
        ("execution.max_violations", GateName.EXECUTION, "execution"),
        ("outcome.windows", GateName.OUTCOME, "outcome"),
        ("outcome.max_incident_rate", GateName.OUTCOME, "outcome"),
        ("outcome.conf", GateName.OUTCOME, "outcome"),
        ("outcome.min_n.7d", GateName.OUTCOME, "outcome"),
    ],
)
def test_missing_config_key_names_itself_and_never_falls_back(
    dotted: str, gate: GateName, artifacts: Any
) -> None:
    """Thiếu khoá ⇒ dừng và nêu ĐÍCH DANH tên khoá.

    Chạy trên tạo tác HỢP LỆ, để gate thật sự đi tới chỗ đọc khoá đó thay vì
    thoát sớm qua đường `refuse` — nếu không, phép kiểm này sẽ xanh cả khi khoá
    không có ai đọc.
    """
    cfg = drop_key(dotted)
    with pytest.raises(ConfigError) as exc:
        run_gate(gate, make_ctx(cfg, **_ARTIFACTS_FOR[artifacts]()))
    assert exc.value.key.startswith(dotted.split(".")[0])


def test_unknown_compare_op_is_rejected_not_defaulted() -> None:
    cfg = with_op("requirements", "≈")
    with pytest.raises(ConfigError) as exc:
        run_gate(GateName.REQUIREMENTS, make_ctx(cfg, criteria=CLEAN_CRITERIA))
    assert exc.value.key == "requirements.compare_op"


def test_load_gates_config_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_gates_config(tmp_path / "khong-ton-tai.yaml")


def test_load_gates_config_refuses_an_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "gates.yaml"
    target.write_text("# rỗng\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_gates_config(target)


# ───────────────────────── dây chuyền ─────────────────────────


def test_chain_stops_at_the_first_failing_gate() -> None:
    """Một verdict `fail` phải chặn được GATE SAU, không chỉ chặn một dòng log."""
    ctx = make_ctx(
        criteria=[_crit(verification_type="vibes")],
        design_matrix=make_matrix(7),
        grid_verdict=FakeGridVerdict(),
        execution=exec_input(CLEAN_DIFF),
        outcome_windows=windows(),
    )
    result = run_chain(ctx)

    assert result.blocked is True
    assert result.stopped_at is GateName.REQUIREMENTS
    assert len(result.verdicts) == 1


def test_chain_runs_all_five_when_nothing_blocks() -> None:
    ctx = make_ctx(
        criteria=CLEAN_CRITERIA,
        design_matrix=make_matrix(7),
        grid_verdict=FakeGridVerdict(),
        execution=exec_input(CLEAN_DIFF),
        outcome_windows=windows(),
    )
    result = run_chain(ctx)

    assert result.blocked is False
    assert result.stopped_at is None
    assert [v.gate for v in result.verdicts] == [
        GateName.REQUIREMENTS,
        GateName.DESIGN,
        GateName.GRID,
        GateName.EXECUTION,
        GateName.OUTCOME,
    ]
    assert all(v.denominator > 0 for v in result.verdicts)


def test_chain_with_no_artifacts_at_all_blocks_immediately() -> None:
    """Mọi tạo tác là `None` phải CHẶN, không phải chạy qua 5 cổng xanh."""
    result = run_chain(make_ctx())
    assert result.blocked is True
    assert result.stopped_at is GateName.REQUIREMENTS
