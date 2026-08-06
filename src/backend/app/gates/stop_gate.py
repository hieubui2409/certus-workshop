"""Stop gate — 9 điều kiện chặn phát hành.

Nguồn: note 02 §7. Điều kiện (0) là cửa bypass, (a)–(i) là chín lý do chặn được
re-derive ở mọi lượt chạy, KỂ CẢ lượt chạy đi qua cửa bypass.

Ba quyết định thiết kế đáng nêu vì sao:

1. **(b) so bằng biên dưới Wilson, không so bằng point estimate.** Đây là mối
   nối mà cả ba tài liệu nền đều thiếu. Bản ghi thật `{killed: 0, survived: 2,
   rate: 1.0}` chặn đúng, nhưng bản ghi ngược `{killed: 2, survived: 0}` cho
   `rate = 0.0` và ĐI LỌT — trong khi Wilson95 của 0/2 là `[0.0, 0.6576]`, tức
   tỉ lệ chấm-cao-sai có thể tới 65,8%, hơn bốn lần trần 0.15.

2. **`blocking_w` là tham số vào, không phải khoá trong `gates.yaml`.** Chỗ ở
   duy nhất của nó là `config/zones.yaml`. Khai lại ở đây là tạo chỗ ở thứ hai
   cho cùng một ngưỡng.

3. **Bypass không phải một cờ cảnh báo.** `assert_release_pass()` RAISE. Một
   hàm trả về `(kết quả, cảnh báo)` rồi hy vọng ai đó đọc `cảnh báo` là hình
   dạng đã đo được là vô hiệu: cảnh báo sinh ra, 0 consumer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.contracts.errors import CertusError
from app.contracts.types import Band

if TYPE_CHECKING:
    from app.gates.registry import GateContext

_OP_KEY = "stop_gate.compare_op"


class BlockReason(BaseModel):
    """Một lý do chặn, mang mã điều kiện của note 02 §7."""

    code: str
    detail: str


class CellRef(BaseModel):
    """Ô lưới, ở dạng stop gate cần để phán xử.

    `declared` trả lời câu hỏi của điều kiện (d): ô này có nằm trong tập khai
    CHỐT LÚC MỞ RUN hay không. So với tập vừa tự sinh là một điều kiện tự thoả
    mãn chính nó và không bao giờ bắn.
    """

    id: str
    zone_id: str
    zone_w: float
    band: str
    stub_alive: bool = False
    declared: bool = False
    stale: bool = False
    mutation_killed_matches_seed: bool = False


class DefectRef(BaseModel):
    id: str
    zone_id: str
    reference: str | None = None


class StopGateInput(BaseModel):
    """Vào của stop gate. Mọi trường đều BẮT BUỘC hoặc mặc-định-chặn.

    Không trường nào mặc định về phía "cho qua": các cờ chứng nhân mang kiểu
    `bool | None` và `None` được đọc thành CHẶN (`witness_unavailable`), vì
    "chưa đo được" và "đo được và ổn" là hai chuyện khác nhau.
    """

    stop_hook_active: bool
    bypass_reason: str | None = None

    #: Đọc từ `config/zones.yaml` — KHÔNG có bản sao trong `config/gates.yaml`.
    blocking_w: float

    cells: list[CellRef] = Field(default_factory=list)
    defects: list[DefectRef] = Field(default_factory=list)

    # (b) calibration
    false_high_killed: int
    false_high_survived: int

    # (d) governance
    declared_digest: str | None = None
    observed_digest: str | None = None

    # (e) chứng nhân
    chain_intact: bool | None = None
    governance_hash_match: bool | None = None
    cross_check_counts: dict[str, int] | None = None
    transcript_parsed: bool | None = None

    # (f) manifest
    bin_manifest_match: bool | None = None

    # (g) drift
    axis_drift_values: list[str] = Field(default_factory=list)

    # (h) Class B
    class_b_mutation_catch: float | None = None
    small_scope_verified: bool | None = None
    interleaving_unknown_after_saturation: int = 0

    # (i) khoá calibration
    calibration_lock_present: bool = False


class StopGateResult(BaseModel):
    """Ra của stop gate.

    `release_pass_allowed` là quyền, không phải gợi ý — cửa duy nhất được phép
    in RELEASE PASS là `assert_release_pass()`, và nó raise.
    """

    blocked: bool
    reasons: list[BlockReason] = Field(default_factory=list)
    bypassed: bool = False
    release_pass_allowed: bool = False
    records: list[dict[str, Any]] = Field(default_factory=list)
    denominator: int = 0
    compare_op: str = "<="
    false_high_lower: float | None = None


class ReleasePassForbidden(CertusError):
    """Cố in RELEASE PASS trên một lượt chạy không còn tư cách."""


def assert_release_pass(result: StopGateResult) -> None:
    """Cổng cấu trúc trước khi bất kỳ ai in RELEASE PASS.

    Bị chặn hoặc đã đi qua cửa bypass ⇒ raise. Không có đường trả về `False` để
    caller lỡ bỏ qua.
    """
    if not result.release_pass_allowed:
        codes = [r.code for r in result.reasons]
        raise ReleasePassForbidden(
            f"CẤM in RELEASE PASS: bypassed={result.bypassed}, lý do chặn={codes}"
        )


def _blocking_cells(inp: StopGateInput) -> list[CellRef]:
    return [c for c in inp.cells if c.zone_w >= inp.blocking_w]


def _check_a(inp: StopGateInput, reasons: list[BlockReason]) -> None:
    """(a) ô `unknown` không có stub sống, trong zone `w >= blocking_w`."""
    offenders = [
        c.id
        for c in _blocking_cells(inp)
        if c.band == Band.UNKNOWN.value and not c.stub_alive
    ]
    if offenders:
        reasons.append(
            BlockReason(
                code="STOP-A",
                detail=f"ô unknown không stub sống trong zone chặn: {offenders}",
            )
        )


def _check_b(inp: StopGateInput, ctx: GateContext, reasons: list[BlockReason]) -> float | None:
    """(b) `false_high_rate` — so bằng BIÊN DƯỚI WILSON, không bằng k/n."""
    threshold = ctx.require("stop_gate.false_high_block")
    conf = ctx.require("stop_gate.conf")
    min_n = ctx.require("stop_gate.false_high_min_n")

    k = inp.false_high_survived
    n = inp.false_high_killed + inp.false_high_survived
    if n == 0:
        reasons.append(
            BlockReason(
                code="STOP-B",
                detail=(
                    "mẫu số calibration rỗng (killed=0, survived=0): chưa đo được tỉ lệ "
                    "chấm-cao-sai; mẫu số rỗng là ĐỎ, không phải xanh"
                ),
            )
        )
        return None

    if n < min_n:
        reasons.append(
            BlockReason(
                code="STOP-B",
                detail=(
                    f"UNVERIFIED: cỡ mẫu calibration n={n} < min_n={min_n}. Point estimate "
                    f"{k / n:.4f} ở cỡ mẫu này không kết luận được gì — đúng ca một lượt "
                    f"{{killed:{inp.false_high_killed}, survived:{k}}} báo 'sạch' rồi đi lọt"
                ),
            )
        )
        return None

    lower = ctx.wilson_lower(k, n, conf)
    ok, op = ctx.compare_by(lower, threshold, _OP_KEY)
    if not ok:
        reasons.append(
            BlockReason(
                code="STOP-B",
                detail=(
                    f"tỉ lệ chấm-cao-sai: k={k}, n={n}, point={k / n:.4f}, "
                    f"biên dưới Wilson({conf})={lower:.4f}, trần đòi {op} {threshold}"
                ),
            )
        )
    return lower


def _check_c(inp: StopGateInput, reasons: list[BlockReason]) -> None:
    """(c) defect trong zone chặn không có tham chiếu."""
    blocking_zone_ids = {c.zone_id for c in _blocking_cells(inp)}
    known_zone_ids = {c.zone_id for c in inp.cells}
    offenders: list[str] = []
    for defect in inp.defects:
        if defect.zone_id not in known_zone_ids:
            offenders.append(f"{defect.id}(zone lạ {defect.zone_id!r})")
            continue
        if defect.zone_id in blocking_zone_ids and not (defect.reference or "").strip():
            offenders.append(defect.id)
    if offenders:
        reasons.append(
            BlockReason(code="STOP-C", detail=f"defect trong zone chặn không có tham chiếu: {offenders}")
        )


def _check_d(inp: StopGateInput, reasons: list[BlockReason]) -> None:
    """(d) `unknown`/`stale` ngoài tập khai chốt lúc mở run."""
    if not (inp.declared_digest or "").strip() or not (inp.observed_digest or "").strip():
        reasons.append(
            BlockReason(
                code="STOP-D",
                detail="thiếu digest tập khai trong governance.lock — không có gì để đối chiếu",
            )
        )
        return
    if inp.declared_digest != inp.observed_digest:
        reasons.append(
            BlockReason(
                code="STOP-D",
                detail=(
                    f"digest tập khai lệch: lock={inp.declared_digest!r}, "
                    f"quan sát={inp.observed_digest!r}"
                ),
            )
        )
    undeclared = [
        c.id for c in inp.cells if (c.band == Band.UNKNOWN.value or c.stale) and not c.declared
    ]
    if undeclared:
        reasons.append(
            BlockReason(
                code="STOP-D",
                detail=f"ô unknown/stale không nằm trong tập khai lúc mở run: {undeclared}",
            )
        )


def _check_e(inp: StopGateInput, reasons: list[BlockReason]) -> None:
    """(e) chứng nhân — fail-closed: thiếu bằng chứng là chặn."""
    missing: list[str] = []
    if inp.chain_intact is not True:
        missing.append("verify_chain")
    if inp.governance_hash_match is not True:
        missing.append("governance_hash")
    if inp.transcript_parsed is not True:
        missing.append("transcript")
    if inp.cross_check_counts is None:
        missing.append("cross_check_counts")
    elif len(set(inp.cross_check_counts.values())) > 1:
        missing.append(f"cross_check lệch đếm {inp.cross_check_counts}")
    if missing:
        reasons.append(
            BlockReason(code="STOP-E", detail=f"witness_unavailable: {missing}")
        )


def _check_f(inp: StopGateInput, reasons: list[BlockReason]) -> None:
    """(f) manifest sha256 của `bin/**`."""
    if inp.bin_manifest_match is not True:
        reasons.append(
            BlockReason(
                code="STOP-F",
                detail=f"manifest sha256 của bin/** không khớp (giá trị={inp.bin_manifest_match!r})",
            )
        )


def _check_g(inp: StopGateInput, reasons: list[BlockReason]) -> None:
    """(g) enum của SUT mọc giá trị mà lưới chưa có."""
    if inp.axis_drift_values:
        reasons.append(
            BlockReason(
                code="STOP-G",
                detail=f"axis drift — SUT có giá trị lưới chưa phủ: {inp.axis_drift_values}",
            )
        )


def _check_h(inp: StopGateInput, ctx: GateContext, reasons: list[BlockReason]) -> None:
    """(h) Class B."""
    floor = ctx.require("stop_gate.class_b_mutation_catch_floor")
    problems: list[str] = []
    if inp.class_b_mutation_catch is None:
        problems.append("mutation-catch bất biến cấm-tuyệt-đối chưa đo")
    elif inp.class_b_mutation_catch < floor:
        problems.append(
            f"mutation-catch={inp.class_b_mutation_catch} < sàn {floor}"
        )
    if inp.small_scope_verified is not True:
        problems.append("small-scope chưa verify")
    if inp.interleaving_unknown_after_saturation > 0:
        problems.append(
            f"{inp.interleaving_unknown_after_saturation} ô interleaving còn unknown sau bão hoà"
        )
    if problems:
        reasons.append(BlockReason(code="STOP-H", detail=f"Class B: {problems}"))


def _check_i(inp: StopGateInput, reasons: list[BlockReason]) -> int:
    """(i) tập-ô-bị-chặn RỖNG cũng là chặn."""
    blocking = _blocking_cells(inp)
    problems: list[str] = []
    if not blocking:
        problems.append(
            f"tập ô bị chặn RỖNG (không ô nào có zone_w >= {inp.blocking_w}) — "
            f"bên bị chấm không được phép làm rỗng tập chặn"
        )
    if not inp.calibration_lock_present:
        problems.append("lock/calibration.lock.json vắng")
    unbacked = [
        c.id
        for c in blocking
        if c.band == Band.HIGH.value and not c.mutation_killed_matches_seed
    ]
    if unbacked:
        problems.append(f"ô high trong zone chặn không có mutation_run killed khớp seed: {unbacked}")
    if problems:
        reasons.append(BlockReason(code="STOP-I", detail="; ".join(problems)))
    return len(blocking)


def evaluate_stop_gate(inp: StopGateInput, ctx: GateContext) -> StopGateResult:
    """Chạy đủ 9 điều kiện, rồi mới xét cửa bypass.

    Thứ tự đó là load-bearing: bypass KHÔNG được bỏ qua phép re-derive. Nó chỉ
    hạ `blocked` xuống `False` và đánh dấu lượt chạy vĩnh viễn mất tư cách
    RELEASE PASS — "in lý do MỘT lần rồi cho qua", đúng một record.
    """
    reasons: list[BlockReason] = []

    _check_a(inp, reasons)
    false_high_lower = _check_b(inp, ctx, reasons)
    _check_c(inp, reasons)
    _check_d(inp, reasons)
    _check_e(inp, reasons)
    _check_f(inp, reasons)
    _check_g(inp, reasons)
    _check_h(inp, ctx, reasons)
    denominator = _check_i(inp, reasons)

    op = ctx.require(_OP_KEY)
    records: list[dict[str, Any]] = []
    blocked = bool(reasons)
    bypassed = False
    release_pass_allowed = not blocked

    if inp.stop_hook_active:
        reason_text = (inp.bypass_reason or "").strip()
        if not reason_text:
            reasons.append(
                BlockReason(
                    code="STOP-BYPASS-NO-REASON",
                    detail="stop_hook_active=True mà không nêu lý do — không có lý do thì không có bypass",
                )
            )
            blocked = True
            release_pass_allowed = False
        else:
            bypassed = True
            blocked = False
            release_pass_allowed = False
            records.append(
                {
                    "type": "gate_bypassed",
                    "reason": reason_text,
                    "blocked_reasons": [r.code for r in reasons],
                }
            )

    return StopGateResult(
        blocked=blocked,
        reasons=reasons,
        bypassed=bypassed,
        release_pass_allowed=release_pass_allowed,
        records=records,
        denominator=denominator,
        compare_op=op,
        false_high_lower=false_high_lower,
    )
