"""Sổ đăng ký và ba cửa công khai của dây chuyền gate.

Vì sao tệp này dispatch bằng `if/return check_*(ctx)` chứ không bằng một bảng
`dict[GateName, handler]`: đăng ký một cái TÊN vào sổ không phải một nơi gọi.
Hệ tham chiếu có `registerGate()` với 0 nơi đăng ký handler thật và `runGate(`
với 0 nơi gọi trong toàn bộ 36 tệp — mà bảng ánh xạ thì trông đầy đủ. Phép đếm
mồ côi ở `tests/test_no_orphans.py` chỉ đếm CẠNH GỌI THẬT (`ast.Call`), nên hình
dạng dưới đây là hình dạng duy nhất đếm được.

Hướng phụ thuộc là một chiều: `registry` → 5 gate + stop gate. Các gate KHÔNG
import ngược lại tệp này; thứ chúng cần (đọc config, so sánh, từ chối) đi qua
`GateContext` được truyền vào. Nhờ vậy không có vòng import nào phải phá bằng
mẹo, và mọi lối vào config của tầng gate đi qua đúng một mối nối.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.contracts.errors import ConfigError
from app.contracts.types import GateName, GateVerdict
from app.gates.design import DesignMatrix, check_design
from app.gates.execution import ExecutionInput, check_execution
from app.gates.grid import GridReviewVerdictLike, check_grid
from app.gates.outcome import OutcomeWindow, check_outcome
from app.gates.requirements import AcceptanceCriterion, check_requirements
from app.gates.stop_gate import StopGateInput, StopGateResult, evaluate_stop_gate

#: Ba cửa mà `orchestrator/pipeline.py` (tầng 4) PHẢI cắm vào ở bước 7.
#: Danh sách này được `tests/test_no_orphans.py` ghim: thêm một hàm chưa đấu nối
#: vào đây làm bộ kiểm ĐỎ, nên chỗ hở không thể vô hình.
PUBLIC_ENTRYPOINTS: tuple[str, ...] = ("run_gate", "run_chain", "run_stop_gate")

#: Thứ tự dây chuyền, lấy từ note 03 §1.1. Thứ tự là load-bearing: gate sau đọc
#: tạo tác mà gate trước đã duyệt.
GATE_ORDER: tuple[GateName, ...] = (
    GateName.REQUIREMENTS,
    GateName.DESIGN,
    GateName.GRID,
    GateName.EXECUTION,
    GateName.OUTCOME,
)

#: Đường dẫn hàm mà tầng 1 phải cấp. Nêu nguyên văn để thông báo lỗi trỏ đúng
#: chỗ phải sửa thay vì chỉ nói "thiếu module".
WILSON_FN_PATH = "app.core.stats.intervals.interval"

WilsonLowerFn = Callable[[int, int, float], float]

_COMPARATORS: Mapping[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _BACKEND_ROOT / "config" / "gates.yaml"


def load_gates_config(path: Path | None = None) -> dict[str, Any]:
    """Nạp `config/gates.yaml`.

    Tệp vắng hoặc rỗng là một SỰ CỐ CẤU HÌNH, không phải "không có luật nào để
    áp" — nên nó dừng ở đây thay vì trả về một dict rỗng mà mọi gate phía sau sẽ
    đọc thành xanh.
    """
    target = _DEFAULT_CONFIG_PATH if path is None else path
    if not target.is_file():
        raise ConfigError(str(target), "tệp cấu hình gate không tồn tại")
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ConfigError(str(target), "nội dung cấu hình gate rỗng hoặc không phải ánh xạ")
    return raw


def require_key(config: Mapping[str, Any], dotted: str) -> Any:
    """Đọc một khoá cấu hình theo đường chấm, KHÔNG có giá trị mặc định.

    Đây là lối vào config duy nhất của tầng gate. Trong `app/gates/` không có
    một lời gọi `.get(khoá, mặc_định)` nào cho ngưỡng: âm thầm rơi về default là
    cách một cái cổng biến thành một cái ống.
    """
    node: Any = config
    walked: list[str] = []
    for part in dotted.split("."):
        walked.append(part)
        if not isinstance(node, Mapping) or part not in node:
            raise ConfigError(dotted, f"khoá vắng tại {'.'.join(walked)!r}")
        node = node[part]
    if node is None:
        raise ConfigError(dotted, "khoá có mặt nhưng giá trị là null")
    return node


def wilson_lower_bound(k: int, n: int, conf: float) -> float:
    """Biên dưới Wilson, lấy từ tầng 1.

    Import trễ vì `core/stats` do cụm khác build và tầng 3 không được ép thứ tự
    build của tầng 1. Nhưng THIẾU NÓ LÀ ĐỎ: không có đường nào ở đây tự tính lấy
    một con số thay thế — tự tính là tạo chỗ ở thứ hai cho cùng một công thức,
    và hai chỗ ở sẽ trôi khỏi nhau.
    """
    try:
        from app.core.stats import intervals
    except ImportError as exc:  # pragma: no cover - phụ thuộc thứ tự build
        raise ConfigError(WILSON_FN_PATH, f"không nạp được module tầng 1: {exc}") from exc
    fn = getattr(intervals, "interval", None)
    if fn is None:
        raise ConfigError(WILSON_FN_PATH, "module tầng 1 không cấp hàm này")
    return float(fn(k, n, conf, method="wilson").lower)


@dataclass(frozen=True)
class GateContext:
    """Mọi thứ một gate được phép đọc.

    `None` ở một tạo tác nghĩa là CHẶN, không nghĩa là bỏ qua — xem
    `GateContext.refuse`. Đây là phòng thủ trực tiếp cho hình dạng đã đo được:
    một dependency bị để `None` ở mọi call-site sản phẩm, còn bản thật chỉ xuất
    hiện trong `conftest.py`.
    """

    config: Mapping[str, Any]
    wilson_lower: WilsonLowerFn
    criteria: Sequence[AcceptanceCriterion] | None = None
    design_matrix: DesignMatrix | None = None
    grid_verdict: GridReviewVerdictLike | None = None
    execution: ExecutionInput | None = None
    outcome_windows: Sequence[OutcomeWindow] | None = None

    def require(self, dotted: str) -> Any:
        return require_key(self.config, dotted)

    def compare_by(self, measured: float, threshold: float, op_key: str) -> tuple[bool, str]:
        """So sánh bằng dấu ĐỌC TỪ CONFIG, và trả luôn dấu đó ra ngoài.

        Trả về cả `op` để gate đặt nó vào `GateVerdict.compare_op`: ca biên (số
        đo bằng đúng ngưỡng) chỉ kiểm được khi dấu so sánh nằm trong hợp đồng.
        """
        op = self.require(op_key)
        if op not in _COMPARATORS:
            raise ConfigError(op_key, f"dấu so sánh không hỗ trợ: {op!r}")
        return _COMPARATORS[op](measured, threshold), op

    def refuse(self, gate: GateName, reason: str, op_key: str) -> GateVerdict:
        """Từ chối có cấu trúc: mẫu số 0, verdict `fail`, `blocked=True`.

        Dùng khi tạo tác vào vắng hoặc rỗng. "Đã soi 40 thứ, thấy 0 lỗi" khác
        hoàn toàn "0 lỗi" trơ trọi, và cái sau không phân biệt được với "chưa
        soi cái nào".
        """
        return GateVerdict(
            gate=gate,
            verdict="fail",
            evidence_tier=None,
            findings=[],
            compare_op=self.require(op_key),
            denominator=0,
            blocked=True,
            reason=reason,
        )


@dataclass(frozen=True)
class ChainResult:
    """Kết quả chạy cả dây chuyền.

    `stopped_at` khác `None` nghĩa là dây chuyền đã DỪNG, không phải "đã chạy
    hết và có một gate đỏ": downstream của gate 1 là gate 2, nên một verdict
    `fail` phải chặn được gate 2 chứ không chỉ chặn được một dòng log.
    """

    verdicts: tuple[GateVerdict, ...]
    blocked: bool
    stopped_at: GateName | None


def run_gate(name: GateName, ctx: GateContext) -> GateVerdict:
    """Chạy đúng một cổng.

    Chuỗi `if` dưới đây là nơi gọi sản phẩm của cả 5 hàm chấm.
    """
    if name is GateName.REQUIREMENTS:
        return check_requirements(ctx)
    if name is GateName.DESIGN:
        return check_design(ctx)
    if name is GateName.GRID:
        return check_grid(ctx)
    if name is GateName.EXECUTION:
        return check_execution(ctx)
    if name is GateName.OUTCOME:
        return check_outcome(ctx)
    raise ConfigError("gate.name", f"không có cổng tên {name!r}")


def run_chain(ctx: GateContext) -> ChainResult:
    """Chạy 5 cổng theo thứ tự, DỪNG ở cổng `fail` đầu tiên.

    Dừng bằng `break` — chặn bằng control-flow, không bằng một cờ trả về rồi hy
    vọng ai đó đọc.
    """
    verdicts: list[GateVerdict] = []
    stopped_at: GateName | None = None
    for name in GATE_ORDER:
        verdict = run_gate(name, ctx)
        verdicts.append(verdict)
        if verdict.verdict == "fail":
            stopped_at = name
            break
    return ChainResult(
        verdicts=tuple(verdicts),
        blocked=stopped_at is not None,
        stopped_at=stopped_at,
    )


def run_stop_gate(inp: StopGateInput, ctx: GateContext) -> StopGateResult:
    """Chạy stop gate — nơi gọi sản phẩm của `evaluate_stop_gate`."""
    return evaluate_stop_gate(inp, ctx)
