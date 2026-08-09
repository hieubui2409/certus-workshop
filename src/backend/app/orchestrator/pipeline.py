"""Luồng phân tích: từ một thư mục mã nguồn tới một phán quyết.

Tệp này là chỗ DUY NHẤT biết thứ tự các bước. Mọi module bên dưới cố tình không
biết mình đứng ở bước nào — nhờ vậy đổi thứ tự là sửa một tệp, không phải sửa
bảy tệp.

Ba luật của luồng:

1. **Bước sau không được chạy trên đầu vào rỗng của bước trước.** Không có
   nhánh "không có dữ liệu thì coi như đạt".
2. **Mọi tỉ lệ sinh ra ở đây đều đi kèm k, n và khoảng.** Một `float` trần rời
   khỏi tệp này là một lỗi hợp đồng.
3. **Việc tính toán là của code, việc diễn giải là của mô hình.** Mô hình không
   bao giờ được hỏi "bao nhiêu ô", chỉ được hỏi "con số này nghĩa là gì".
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.agent.claims import ClaimParseError, extract_claims_json, parse_claims
from app.agent.context import load_prompt, render_prompt
from app.agent.llm import LLMClient, LLMResponse
from app.agent.persona import PersonaStore
from app.agent.retrieval import build_context
from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ClaimOut,
    CoverageOut,
    RateOut,
    StreamEvent,
    ZoneOut,
)
from app.contracts.errors import CassetteMissError, CertusError, ConfigError
from app.contracts.types import Band, Cell, Claim, GateVerdict, Interval
from app.gates.registry import (
    GATE_ORDER,
    GateContext,
    load_gates_config,
    run_gate,
    wilson_lower_bound,
)
from app.core.grid.axis_admit import is_vendor_path
from app.core.grid.cells import cell_id as make_cell_id
from app.core.grid.cells import enumerate_t_wise
from app.core.grid.project import project_cell
from app.core.grid.rollup import (
    evaluate_floor,
    load_band_scores,
    load_floors,
    min_per_zone,
    risk_weighted_coverage,
)
from app.core.grid.zones import load_zone_config, require_zone
from app.core.stats.intervals import interval
from app.orchestrator.observe import (
    load_mutation_artifact,
    lookup,
    mutation_run_for_cell,
    observations_for_cells,
    scan_tests,
)
from app.orchestrator.provision import ProvisionPlan, detect_plan, run_suite
from app.observability import tracing
from app.observability.logging import get_logger
from app.policy.data_policy import load_policy
from app.settings import Settings, settings as default_settings

log = get_logger()


class SuiteRunFailed(CertusError):
    """Bộ kiểm của repo đích không chạy được — chưa đo được gì.

    Tách khỏi "test đỏ": test đỏ là một quan sát hợp lệ (`known_failure`), còn
    cái này nghĩa là pytest chưa từng chạy tới phần thân. Fail-closed ở đây để
    pipeline không phát ra một bảng grid trông như đã đo.
    """


@dataclass(frozen=True)
class _GridVerdictForGate:
    """Tạo tác mà cổng `grid` đọc, dựng từ kết quả CÓ THẬT của lượt chạy này.

    Khai bằng dataclass riêng thay vì nhét thêm trường vào `CoverageOut`: cổng
    `grid` khai hợp đồng của nó bằng Protocol (`GridReviewVerdictLike`), và một
    lớp chuyển đổi rõ ràng ở đây giữ cho hai bên đổi độc lập được. Mọi trường
    dưới đây đều đến từ số đã tính, không có cái nào bịa — đặc biệt là
    `blocking_zones`: cổng CHẶN khi tập này rỗng, nên bơm vào một danh sách
    không rỗng cho "đẹp" là tự tay tắt đúng cái luật cần chạy.
    """

    risk_band: str
    cells_total: int
    cells_scored: int
    blocking_zones: Sequence[str]
    min_per_zone: Mapping[str, float]
    source_file: str
    source_line: int


def _worst_band_name(cells: Sequence[Cell]) -> str:
    """Band TỆ NHẤT trong lưới — không phải band trung bình.

    Trung bình cho phép một vùng an toàn che một vùng nguy hiểm ở chỗ khác, đúng
    thứ `CoverageTriptych` từ chối làm. `unknown` xếp tệ nhất: nó nằm TRONG mẫu
    số và chấm 0, khác hẳn `N/A` (ngoài mẫu số).
    """
    order = [Band.UNKNOWN, Band.STUB, Band.LOW, Band.MED, Band.HIGH]
    present = [c.band for c in cells if c.band is not Band.NA]
    if not present:
        return Band.UNKNOWN.value
    return min(present, key=lambda b: order.index(b) if b in order else 0).value


# --------------------------------------------------------------------------
# Khám phá trục
# --------------------------------------------------------------------------


@dataclass
class Axes:
    """Các trục rủi ro tìm được trong repo, kèm nguồn gốc.

    `source` không phải trang trí: một trục suy ra từ Enum trong code có tư cách
    khác hẳn một trục do mô hình đề xuất, và cổng đối xử với chúng khác nhau.
    """

    values: dict[str, list[str]] = field(default_factory=dict)
    source: dict[str, str] = field(default_factory=dict)

    def size(self) -> int:
        return len(self.values)


_ENUM_HINTS = ("Tier", "Zone", "Method", "Type", "Status", "Kind", "Mode", "Level")

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _axis_name(class_name: str) -> str:
    """Tên trục = snake_case của tên Enum, KHÔNG phải `lower()` trần.

    `lower()` nuốt ranh giới từ: `PaymentMethod` → `paymentmethod`, trong khi
    `zones.yaml` (và mọi predicate zone do người viết) dùng `payment_method`.
    Hai cách viết cùng một trục là cách kinh điển để tập chặn IM LẶNG rỗng —
    predicate không khớp key nào nên mọi ô rơi về catch-all, và không có gì
    báo rằng zone rủi ro chưa từng được điền.
    """
    return _CAMEL_BOUNDARY.sub("_", class_name).lower()


def discover_axes(root: Path) -> Axes:
    """Đọc Enum trong mã nguồn để dựng trục. Deterministic, không hỏi mô hình.

    Trục là MẪU SỐ của toàn bộ phần chấm điểm phía sau. Để mô hình sinh mẫu số
    nghĩa là mẫu số đổi giữa hai lượt chạy trên cùng một repo, và mọi tỉ lệ phía
    sau mất khả năng so sánh.
    """
    import ast

    axes = Axes()
    for py in sorted(root.rglob("*.py")):
        if is_vendor_path(py, root):
            continue
        if "test" in py.parts or py.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
            is_enum = any("Enum" in b for b in bases) or node.name.endswith(_ENUM_HINTS)
            if not is_enum:
                continue
            members = [
                t.id.lower()
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                for t in stmt.targets
                if isinstance(t, ast.Name) and not t.id.startswith("_")
            ]
            if len(members) >= 2:
                axis = _axis_name(node.name)
                axes.values[axis] = members
                axes.source[axis] = f"{py.relative_to(root)}::{node.name}"
    return axes


def restrict_axes(axes: Axes, confirmed: Mapping[str, Sequence[str]]) -> Axes:
    """Thu hẹp trục KHÁM PHÁ ĐƯỢC xuống tập người dùng XÁC NHẬN (HITL).

    Chỉ giữ trục nằm trong CẢ hai (khám phá ∩ xác nhận): người dùng CHỌN trong
    số trục code đã suy ra, KHÔNG thêm được trục không có Enum nào đứng sau — mẫu
    số phải neo vào code, đó là lý do `discover_axes` không hỏi mô hình. Với mỗi
    trục giữ lại, lọc member theo danh sách xác nhận nhưng GIỮ THỨ TỰ KHÁM PHÁ
    (axis-lock ổn định); danh sách rỗng ⇒ giữ mọi member. Trục còn dưới 2 giá trị
    bị bỏ hẳn — một trục một-giá-trị không phân biệt được gì, giữ lại chỉ làm hỏng
    phép đếm t-wise. `source` ghi thêm 'human-confirmed' để cổng phân biệt trục đã
    qua HITL với trục thô.
    """
    out = Axes()
    for axis, members in axes.values.items():
        if axis not in confirmed:
            continue
        want = list(confirmed[axis])
        kept = [m for m in members if m in want] if want else list(members)
        if len(kept) < 2:
            continue
        out.values[axis] = kept
        out.source[axis] = f"human-confirmed · {axes.source.get(axis, '?')}"
    return out


def select_axes(
    discovered: Axes,
    rules: Sequence[Mapping[str, Any]],
    *,
    confirmed_axes: Mapping[str, Sequence[str]] | None = None,
    candidates: Sequence[Any] | None = None,
) -> tuple[Axes, dict[str, Any]]:
    """Chọn tập trục bằng engine ToT (đề xuất → admit → beam), THAY discover-giữ-hết.

    Ba nhánh, đúng một chạy:
    - `confirmed_axes` có ⇒ NGƯỜI đã chốt (HITL): thu hẹp UNIVERSE ứng viên về đúng
      lựa chọn của họ. Ý người thắng beam.
    - ngược lại chạy beam ρ trên ứng viên; admit loại `asserted` (branch) khỏi default,
      giữ `retrieved`/`derived`. Beam tỉa nhiễu ở đâu zones có tín hiệu.
    - SÀN VIABILITY: beam lock < 2 trục (zones không mã hoá rủi ro repo này → ρ=0)
      ⇒ rơi về TẬP ENUM khám phá (mẫu số sạch nhất, không rơi về branch asserted).

    `candidates`: tập ứng viên ĐA NGUỒN (enum+config+branch — `axis_sources`). None ⇒
    chỉ Enum, dựng từ `discovered` — đường REPO MẪU: universe = discovered nên axis_lock/
    cell_id y hệt baseline → cassette/golden bất biến. Có ⇒ đường REPO THẬT.

    LUÔN dựng lại theo THỨ TỰ candidate (enum→config→branch); Enum-only ⇒ thứ tự này
    trùng thứ tự khám phá, nên repo có tập trục không đổi ra cell_id y hệt.
    """
    from app.core.grid.axis_admit import AxisCandidate, load_admit_config
    from app.core.grid.axis_score import load_search_params
    from app.core.grid.axis_search import search_axes

    # Enum-only mặc định: MỘT nguồn sự thật cho tập Enum + thứ tự khám phá.
    if candidates is None:
        candidates = [
            AxisCandidate(
                name=n, members=tuple(v), ref=discovered.source.get(n, "?"),
                tier="retrieved", origin="enum",
            )
            for n, v in discovered.values.items()
        ]

    # Universe = mọi ứng viên dựng thành Axes theo thứ tự candidate. HITL thu hẹp trên
    # ĐÂY (không chỉ Enum) nên người dùng chốt được cả trục config/branch.
    universe = Axes()
    for c in candidates:
        universe.values[c.name] = list(c.members)
        universe.source[c.name] = c.ref

    if confirmed_axes is not None:
        axes = restrict_axes(universe, confirmed_axes)
        return axes, {"engine": "hitl", "quarantined": [], "rejected": []}

    result = search_axes(
        candidates, fixed_axes={}, rules=rules,
        params=load_search_params(), admit_config=load_admit_config(),
    )
    locked = set(result.locked_axes)
    floored = len(locked) < 2
    if floored:
        locked = set(discovered.values)

    axes = Axes()
    order: Sequence[tuple[str, Sequence[str]]] = (
        list(discovered.values.items()) if floored
        else [(c.name, c.members) for c in candidates]
    )
    for name, members in order:
        if name in locked and name not in axes.values:
            axes.values[name] = list(members)
            axes.source[name] = universe.source.get(name, discovered.source.get(name, "?"))
    meta = {
        "engine": "floor" if floored else "tot",
        "quarantined": [q.axis for q in result.quarantined],
        "rejected": [{"axis": a, "reason": r} for a, r in result.rejected],
    }
    return axes, meta


def candidates_for(root: Path, discovered: Axes, *, is_sample: bool) -> list[Any] | None:
    """Ứng viên đa nguồn cho REPO THẬT; None cho REPO MẪU.

    Repo mẫu (`req.target`, dưới targets_dir) phải ra tập trục y HỆT baseline để
    cassette/golden bất biến — nên KHÔNG bơm config/branch, giữ Enum-only. Repo thật
    (`req.upload_id`, dưới workspace_dir) bật đa nguồn để engine + HITL có gì mà tỉa;
    repo thật KHÔNG có cassette (chạy live) nên đổi tập trục không phá gì.
    """
    if is_sample:
        return None
    from app.core.grid.axis_sources import propose_candidates

    return propose_candidates(root, discovered.values, discovered.source)


# --------------------------------------------------------------------------
# Quan sát
# --------------------------------------------------------------------------


def observe_cells(
    axes: Axes,
    *,
    zones: list[Mapping[str, Any]],
    blocking_w: float,
    observations: Mapping[tuple[str, ...], Mapping[str, Any]] | None = None,
    mutation: Mapping[str, Any] | None = None,
) -> list[Cell]:
    """Liệt kê ô rồi chiếu band cho từng ô.

    Ô không có quan sát nào KHÔNG biến mất — nó thành `unknown`. Ô biến mất là
    ô rời khỏi mẫu số, và mẫu số nhỏ đi thì mọi tỉ lệ đẹp lên mà không ai làm gì.

    `mutation` là artifact mutation precomputed (hoặc None). Nó chỉ được tiêm vào
    ô THUỘC zone mà artifact khai, và chỉ khi ô ấy đã có quan sát — một ô chưa có
    test không thể được nâng band bằng một verdict mutation.
    """
    if axes.size() < 2:
        raise CertusError(
            f"chỉ tìm được {axes.size()} trục rủi ro — dưới 2 trục thì không có "
            "cặp nào để phủ, và mọi con số grid phía sau vô nghĩa"
        )
    obs = observations or {}
    # Axis lock = thứ tự KHÁM PHÁ, không phải sorted. discover_axes duyệt tệp
    # theo đường dẫn đã sắp nên thứ tự này ổn định giữa hai lượt chạy, và
    # enumerate_t_wise sinh tên trục theo đúng thứ tự đó.
    axis_lock = list(axes.values)
    cells: list[Cell] = []
    for names, values in enumerate_t_wise(axes.values, t=2):
        cid = make_cell_id((names, values), axis_lock)
        combo = dict(zip(names, values, strict=True))
        zone = require_zone(combo, zones)
        observation = lookup(obs, values) if obs else None
        if mutation is not None and observation is not None:
            mrun = mutation_run_for_cell(
                mutation, zone_id=str(zone["id"]), cell_id=cid
            )
            if mrun is not None:
                # Bản sao — không vá vào bảng quan sát dùng chung: cùng một
                # value-tuple có thể tra ra cho nhiều ô, và chỉ ô đúng zone mới
                # được mang mutation_run.
                observation = {
                    **observation,
                    "mutation_run": mrun,
                    "calibration_seed_id": mrun["seed_id"],
                }
        cells.append(
            project_cell(
                cell_id=cid,
                axes=combo,
                zone=zone,
                blocking_w=blocking_w,
                observation=observation,
            )
        )
    return cells


def _analyze_nonce(req: AnalyzeRequest) -> str:
    """Nonce TẤT ĐỊNH theo (repo, câu hỏi).

    Nonce đi vào prompt, prompt đi vào `cassette_key` (hash cả messages). Một
    nonce ngẫu nhiên làm MỌI lượt chạy ra một khoá khác nhau → cassette không
    bao giờ hit → replay chết, và cả kiến trúc cassette-mặc-định sụp. Tất định
    theo (target/upload_id, question) giữ replay chạy được, mà vẫn là một giá
    trị mô hình phải chép lại đúng để chứng minh nó đã đọc khối chỉ thị này.
    """
    seed = f"{req.target or req.upload_id or req.local_path}|{req.question}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _format_artifacts(coverage: CoverageOut) -> str:
    """Gói các con số ĐÃ TÍNH thành khối chữ cho mô hình DIỄN GIẢI.

    Luật số 3 của luồng: model đọc số, không tính số. Ba tầng mẫu số đứng cạnh
    nhau và không gộp — đúng thứ prompt dặn model giữ nguyên.
    """
    lines: list[str] = []
    if coverage.line is not None:
        iv = coverage.line.interval
        lines.append(
            f"- Line coverage: {coverage.line.k}/{coverage.line.n} = "
            f"{coverage.line.point:.1%}, Wilson [{iv.lower:.3f}, {iv.upper:.3f}]"
        )
    lines.append(
        f"- Grid coverage: {coverage.grid.k}/{coverage.grid.n} = "
        f"{coverage.grid.point:.1%} ô rủi ro đã phủ"
    )
    lines.append(
        f"- Ô N/A: {coverage.cells_na} · ô unknown: {coverage.cells_unknown} · "
        f"tổng {coverage.cells_total} ô"
    )
    for z in coverage.per_zone:
        lines.append(
            f"- Zone {z.zone_id} (w={z.weight}): score={z.score:.3f} trên "
            f"{z.cells_scoreable}/{z.cells_total} ô chấm được"
        )
    return "\n".join(lines)


def rate(name: str, k: int, n: int, *, conf: float = 0.95) -> RateOut:
    """Gói một tỉ lệ kèm mẫu số và khoảng. Không có lối đi tắt trả float trần."""
    if n <= 0:
        raise CertusError(
            f"tỉ lệ {name!r} có mẫu số 0 — không có phép tính nào cứu được điều đó"
        )
    iv = interval(k, n, conf=conf, method="wilson")
    flags: list[str] = []
    if n < 10:
        flags.append("n-too-small")
    if iv.upper - iv.lower > 0.30:
        flags.append("interval-wide")
    if getattr(iv, "saturated", False):
        flags.append("interval-saturated")
    return RateOut(
        name=name,
        k=k,
        n=n,
        point=k / n,
        interval=iv if isinstance(iv, Interval) else Interval(**dict(iv)),
        flags=flags,
    )


# --------------------------------------------------------------------------
# Luồng
# --------------------------------------------------------------------------

#: Chữ đọc được cho mỗi cờ. Hợp đồng bắt cảnh báo hiện thành CÂU, không phải
#: mã — một mã bắt người đọc tra bảng, và trong thực tế họ không tra.
_WARNING_TEXT = {
    "n-too-small": "mẫu số quá nhỏ để kết luận: khoảng tin cậy rộng hơn chính con số",
    "interval-wide": "khoảng tin cậy rộng hơn 30 điểm phần trăm — con số này chưa nói được gì",
    "interval-saturated": "khoảng đã tràn ra ngoài [0,1] rồi bị cắt về; đừng đọc nó như một khoảng hẹp",
}

STAGES = (
    "resolve_target",
    "apply_data_policy",
    "discover_axes",
    "run_tests",
    "read_coverage",
    "project_grid",
    "rollup",
    "run_gates",
    "explain",
)


@dataclass
class PipelineResult:
    response: AnalyzeResponse
    events: list[StreamEvent] = field(default_factory=list)


class Pipeline:
    """Chạy một lượt phân tích và phát sự kiện dọc đường.

    Được viết ở dạng async generator để UI thấy tiến trình thay vì một vòng
    xoay bốn phút. Một tiến trình không quan sát được thì mọi lỗi trong nó
    trông giống hệt nhau: "chậm".
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.cfg = settings or default_settings
        self._seq = 0

    def _event(self, kind: str, trace_id: str, **payload: Any) -> StreamEvent:
        self._seq += 1
        return StreamEvent(seq=self._seq, kind=kind, trace_id=trace_id, payload=payload)

    def _step(self, trace_id: str, name: str, status: str = "done", **extra: Any):
        """Một bước của luồng. `step` là số thứ tự trong STAGES, không phải số đếm
        tự do: hai lượt chạy phải đánh số cùng một bước giống nhau."""
        return self._event(
            "step", trace_id,
            step=STAGES.index(name) + 1 if name in STAGES else 0,
            name=name, status=status, **extra,
        )

    def _log(self, trace_id: str, level: str, msg: str):
        return self._event("log", trace_id, level=level, msg=msg)

    @staticmethod
    def _unwrap_single_dir(root: Path) -> Path:
        """Đi xuống khi bản giải nén chỉ có ĐÚNG MỘT thư mục con.

        `git archive` và nút "Download ZIP" của GitHub đều bọc toàn bộ repo
        trong một thư mục mang tên repo, nên sau khi giải nén thì `pyproject
        .toml`/`uv.lock`/`tests/` nằm sâu một tầng. Không đi xuống thì mọi thứ
        dò theo gốc repo đều trượt: `detect_plan` không thấy lockfile nên chọn
        interpreter của CERTUS, rồi pytest chết ở collect — và lỗi hiện ra là
        "thiếu dependency", không phải "tôi tìm sai chỗ".

        Chỉ đi xuống khi có ĐÚNG một thư mục và KHÔNG có tệp nào ở cùng tầng:
        có tệp nghĩa là gốc repo thật sự ở đây (zip trải phẳng), và đi xuống sẽ
        bỏ qua chính nó. Chỉ một tầng — nhiều tầng là đoán mò.
        """
        entries = [p for p in root.iterdir() if not p.name.startswith(".")]
        dirs = [p for p in entries if p.is_dir()]
        if len(entries) == 1 and len(dirs) == 1:
            return dirs[0]
        return root

    def resolve_target(self, req: AnalyzeRequest) -> Path:
        sources = [bool(req.target), bool(req.upload_id), bool(req.local_path)]
        if sum(sources) != 1:
            raise CertusError(
                "phải có ĐÚNG một trong `target`, `upload_id` và `local_path`. Nhận "
                "nhiều hơn một (hoặc không cái nào) là để ngỏ chuyện nội dung người "
                "dùng đưa vào được đối xử như repo mẫu đáng tin"
            )
        if req.local_path:
            # Không có tường chứa nào ở đây — CÓ CHỦ ĐÍCH, và giới hạn của nó
            # phải nói rõ: đường này cho người dùng trỏ vào BẤT KỲ thư mục nào
            # trên máy chạy backend. An toàn vì backend chạy localhost trên máy
            # của chính họ; một bản nhiều người dùng phải tắt hẳn đường này chứ
            # không phải rào nó, vì "thư mục nào là của ai" không trả lời được
            # từ trong tiến trình này.
            root = Path(req.local_path).expanduser().resolve()
            if not root.is_dir():
                raise CertusError(
                    f"không có thư mục {root} — kiểm tra lại đường dẫn (phải là "
                    "đường dẫn trên máy đang chạy backend, không phải máy khác)"
                )
            return root
        if req.target:
            root = (self.cfg.targets_dir / req.target).resolve()
            if self.cfg.targets_dir.resolve() not in root.parents:
                raise CertusError(f"target {req.target!r} nằm ngoài thư mục repo mẫu")
        else:
            root = (self.cfg.workspace_dir / str(req.upload_id)).resolve()
            # Nhánh `target` kiểm chứa, nhánh này thì KHÔNG — cùng một lỗ hổng
            # đã vá cho `target`: `upload_id="../../fixtures/targets/payments"`
            # resolve() thoát khỏi workspace rồi pytest chạy trên thư mục bất kỳ
            # (→ code-exec). upload_id là chuỗi client gửi tự do, phải bị chặn
            # đúng như target.
            if self.cfg.workspace_dir.resolve() not in root.parents:
                raise CertusError(
                    f"upload_id {req.upload_id!r} nằm ngoài thư mục workspace"
                )
        if not root.is_dir():
            raise CertusError(f"không có thư mục {root}")
        return self._unwrap_single_dir(root) if req.upload_id else root

    async def run(self, req: AnalyzeRequest) -> AsyncIterator[StreamEvent]:
        started = time.time()
        final: dict[str, Any] | None = None
        with tracing.start_trace() as trace_id:
            try:
                async for ev in self._run_inner(req, trace_id):
                    # `done` phải đếm claims thật và blocked thật, không phải
                    # hằng số 0/False như khi tầng agent còn chưa nối. Đọc lại
                    # từ step `explain` cuối cùng — chỗ duy nhất giữ response.
                    if (
                        ev.kind == "step"
                        and ev.payload.get("name") == "explain"
                        and "response" in ev.payload
                    ):
                        final = ev.payload["response"]
                    yield ev
            except CertusError as exc:
                # Lỗi có cấu trúc đi ra bằng đúng dòng stream, không nuốt.
                yield self._event(
                    "error", trace_id, code=type(exc).__name__, msg=str(exc)
                )
                return
            yield self._event(
                "done", trace_id,
                claims=len(final["claims"]) if final else 0,
                blocked=(final["verdict"] == "blocked") if final else False,
                elapsed_s=round(time.time() - started, 3),
            )

    async def _run_inner(
        self, req: AnalyzeRequest, trace_id: str
    ) -> AsyncIterator[StreamEvent]:
        yield self._log(
            trace_id, "INFO",
            f"bắt đầu phân tích {req.target or req.upload_id or req.local_path}",
        )

        yield self._step(trace_id, "resolve_target", "running")
        root = self.resolve_target(req)
        yield self._step(trace_id, "resolve_target", path=str(root))

        # Repo THẬT (upload) phải qua bước chọn trục. Proposer đa nguồn trên repo lạ
        # thường floor về rất nhiều trục Enum (zones là của repo mẫu), auto-analyze sẽ
        # nổ cartesian và mọi con số grid vô nghĩa. Buộc HITL: người chốt 2–4 trục qua
        # /axes/discover rồi gửi confirmed_axes. Repo mẫu (target) miễn — trục cố định.
        if (req.upload_id or req.local_path) and not req.confirmed_axes:
            raise CertusError(
                "repo thật phải CHỌN TRỤC trước khi phân tích: gọi "
                "/api/axes/discover, chốt 2–4 trục rồi gửi lại kèm confirmed_axes. "
                "(Repo mẫu thì không cần — trục đã cố định để bài giảng tất định.)"
            )

        # Chính sách dữ liệu chạy TRƯỚC mọi thứ chạm tới mô hình.
        policy = load_policy()
        sent, held = [], {}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            # Phụ thuộc bên thứ ba không phải DỮ LIỆU của người dùng: quét
            # `.venv` ở đây làm bảng "đã gửi/đã giữ" ngập hàng vạn file thư viện
            # và chôn mất đúng những tệp mà chính sách cần cho người đọc thấy.
            if is_vendor_path(path, root):
                continue
            rel = str(path.relative_to(root))
            decision = policy.decide(rel)
            (sent.append(rel) if decision.allowed else held.setdefault(rel, decision.reason))
        yield self._step(
            trace_id, "apply_data_policy",
            files_sent=len(sent), files_held=len(held),
        )

        # load_zone_config đã compile sẵn — không ai được cầm rules chưa compile.
        # Nạp TRƯỚC chọn trục: engine ρ cần rules zone để chấm mật độ rủi ro.
        zone_cfg = load_zone_config()
        blocking_w = zone_cfg.blocking_w
        cfg_zones = zone_cfg.rules

        # Chọn trục bằng engine ToT (thay discover-giữ-hết). `confirmed_axes` (nếu
        # có) là ý NGƯỜI sau khi xem đề xuất — thắng beam. Không có ⇒ beam ρ + sàn
        # viability. select_axes giữ THỨ TỰ KHÁM PHÁ nên repo có tập trục không đổi
        # (mọi repo mẫu hiện tại) ra cell_id y hệt → cassette/golden bất biến.
        discovered = discover_axes(root)
        candidates = candidates_for(root, discovered, is_sample=bool(req.target))
        axes, axis_meta = select_axes(
            discovered, cfg_zones, confirmed_axes=req.confirmed_axes, candidates=candidates
        )
        yield self._step(
            trace_id, "discover_axes",
            axes={k: len(v) for k, v in axes.values.items()},
            source=axes.source, **axis_meta,
        )
        tests = scan_tests(root)

        # Dựng môi trường CHẠY ĐƯỢC cho repo lạ, rồi chạy bộ kiểm của nó, phát
        # từng dòng log ngay khi nó ra. Một bộ kiểm thật mất 2–3 phút; im lặng
        # 3 phút không phân biệt được với treo, nên log phải chảy chứ không dồn.
        plan = detect_plan(root, user_argv=req.test_command)
        yield self._event(
            "log", trace_id, level="INFO",
            msg=f"môi trường chạy bộ kiểm: {plan.kind} — {plan.reason}",
        )
        for line in plan.steps:
            yield self._event("log", trace_id, level="INFO", msg=f"  · {line}")
        yield self._event(
            "log", trace_id, level="INFO", msg=f"$ {' '.join(plan.argv)}"
        )

        # Bộ kiểm chạy trong một luồng riêng (nó là subprocess đồng bộ) còn
        # generator này phải nhả sự kiện giữa chừng. Hàng đợi nối hai nhịp đó —
        # cùng cơ chế đã dùng cho token của bước diễn giải.
        log_queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _emit(line: str) -> None:
            loop.call_soon_threadsafe(log_queue.put_nowait, line)

        async def _run() -> tuple[int, set[str], tuple[int, int]]:
            try:
                return await asyncio.to_thread(
                    run_target_suite, root, plan, req.test_env, _emit
                )
            finally:
                loop.call_soon_threadsafe(log_queue.put_nowait, None)

        suite_task = asyncio.create_task(_run())
        while True:
            line = await log_queue.get()
            if line is None:
                break
            yield self._event("log", trace_id, level="TEST", msg=line)
        suite_exit, cov_suite, (lines_hit, lines_total) = await suite_task

        yield self._step(
            trace_id, "run_tests",
            test_functions=len(tests), exit_code=suite_exit,
            lines_covered=len(cov_suite),
            lines_hit=lines_hit, lines_total=lines_total,
            env_kind=plan.kind, command=" ".join(plan.argv),
        )
        # `read_coverage` là bước 5 trong STAGES. Nó gộp VẬT LÝ vào run_tests (cùng
        # một `run_target_suite`), nhưng vẫn phát THÀNH bước riêng — nếu không, sidebar
        # hiện "chưa chạy" cho một bước thực sự đã chạy, đúng cái nhầm mà StepProgress
        # được viết ra để tránh.
        yield self._step(
            trace_id, "read_coverage",
            lines_hit=lines_hit, lines_total=lines_total,
        )
        # `code_path` phải là một ký hiệu CÓ THẬT trong repo đang chấm. Bản cũ
        # ghim cứng `"checkout"` cho mọi repo — repo nào không có tên ấy thì
        # không ô nào chạm tới, rơi `coverage_mismatch` toàn bảng, và grid ra
        # full unknown dù bộ kiểm chạy hoàn hảo.
        entry_symbol = infer_entry_symbol(root, cov_suite)
        if entry_symbol is None:
            raise CertusError(
                "không neo được `code_path` vào ký hiệu nào của repo: bộ kiểm chạy "
                "nhưng không chạm hàm cấp module nào. Mọi ô sẽ là 'chưa ai canh' — "
                "đó là chuyện thiếu bằng chứng, không phải một phép đo."
            )
        obs_table = observations_for_cells(
            tests,
            code_path=entry_symbol,
            cov_suite=cov_suite,
            suite_exit_code=suite_exit,
        )
        # Mutation replay: chỉ cho repo mẫu (target), không cho upload — upload
        # chưa từng qua lượt mutmut của host nên KHÔNG có artifact, và đó là
        # fail-closed đúng, không phải thiếu sót.
        mutation_artifact = (
            load_mutation_artifact(req.target, self.cfg.mutations_dir)
            if req.target
            else None
        )
        cells = observe_cells(
            axes,
            zones=cfg_zones,
            blocking_w=blocking_w,
            observations=obs_table,
            mutation=mutation_artifact,
        )
        # Trần phát ô — có thật, vì một lưới 6 trục sinh hàng nghìn ô và đổ hết
        # qua SSE thì trình duyệt đứng hình. Nhưng một trần IM LẶNG là chỗ mẫu
        # số co lại mà không ai biết: đo trên document-intake với 6 trục, lưới
        # thật có 421 ô còn UI in "Ô được liệt kê 200" — vì UI đếm số event
        # `cell` nó nhận được, trong khi `coverage.grid` vẫn chia cho 421. Hai
        # con số trên cùng một màn hình nói hai mẫu số khác nhau.
        #
        # Nên trần vẫn còn, nhưng nó phải TỰ KHAI: `cells_emitted` cho biết đã
        # phát bao nhiêu, `cells` cho biết lưới thật to bao nhiêu, và khi hai
        # cái lệch thì đi kèm một cảnh báo đọc được.
        CELL_EMIT_CAP = 400
        for c in cells[:CELL_EMIT_CAP]:
            yield self._event("cell", trace_id, cell=c.model_dump(mode="json"))
        if len(cells) > CELL_EMIT_CAP:
            yield self._event(
                "warning",
                trace_id,
                code="cells-truncated",
                msg=(
                    f"lưới có {len(cells)} ô nhưng chỉ {CELL_EMIT_CAP} ô đầu được "
                    f"gửi lên giao diện (trần hiển thị). Mẫu số THẬT của "
                    f"`grid_coverage` vẫn là {len(cells)} ô — đọc con số ở tab "
                    "'Ba tầng mẫu số', đừng đếm ô trên bản đồ nhiệt."
                ),
            )
        yield self._step(
            trace_id,
            "project_grid",
            cells=len(cells),
            cells_emitted=min(len(cells), CELL_EMIT_CAP),
        )

        band_scores = load_band_scores()
        rw = risk_weighted_coverage(cells, band_scores)
        per_zone = min_per_zone(cells, band_scores)
        yield self._step(trace_id, "rollup", risk_weighted=rw, zones=len(per_zone))

        covered = sum(1 for c in cells if c.band in (Band.HIGH, Band.MED))
        scoreable = sum(1 for c in cells if c.band is not Band.NA)
        grid_rate = rate("grid_coverage", covered, max(scoreable, 1))

        line_rate = (
            rate("line_coverage", lines_hit, lines_total) if lines_total else None
        )

        coverage = CoverageOut(
            line=line_rate,
            grid=grid_rate,
            risk_weighted=rw,
            per_zone=[
                ZoneOut(
                    zone_id=zid,
                    weight=float(z["w"]),
                    # Khoá phải khớp ĐÚNG cái min_per_zone trả ra (worst_score,
                    # cells_scored). Đọc `.get("min_score", 0.0)` từng nuốt lỗi
                    # bằng default: sai khoá vẫn ra 0.0 nên score mọi zone luôn
                    # 0.0 mà không ai thấy. Index thẳng để sai khoá thì nổ.
                    score=float(z["worst_score"]),
                    cells_total=int(z["cells_total"]),
                    cells_scoreable=int(z["cells_scored"]),
                )
                for zid, z in per_zone.items()
            ],
            cells=cells,
            cells_total=len(cells),
            cells_na=sum(1 for c in cells if c.band is Band.NA),
            cells_unknown=sum(1 for c in cells if c.band is Band.UNKNOWN),
        )

        # ── gate: sàn grid per-zone — bước 8, CHẠY TRƯỚC bước diễn giải ─────
        # Cổng chỉ đọc `per_zone` (đã có ngay trên), không đọc claim nào, nên nó
        # xong được từ đây. Trước đây khối này nằm SAU `explain`, khiến bước 9
        # phát `running` trước khi bước 8 phát `done` — thanh tiến trình nhảy
        # ngược 9 → 8 → 9. Chạy đúng thứ tự thì bước 8 đóng trước khi bước 9 mở.
        floor_verdicts = evaluate_floor(per_zone, load_floors())
        blocking_failures = [
            zid for zid, v in floor_verdicts.items()
            if per_zone[zid]["w"] >= blocking_w and not v["meets_floor"]
        ]
        for zid, v in floor_verdicts.items():
            yield self._event(
                "gate", trace_id, zone_id=zid,
                blocking=per_zone[zid]["w"] >= blocking_w, **v,
            )
        blocked = bool(blocking_failures)

        # ── chuỗi 5 cổng — requirements · design · grid · execution · outcome ──
        # Đây là thứ tab "Chuỗi cổng" của UI vẽ. Trước bản này pipeline không gọi
        # nó, nên tab đó RỖNG kể cả sau một lượt chạy 9/9 — một panel trống đọc
        # y hệt một panel hỏng, và cái nó đang giấu chính là bài học chính của nó.
        #
        # Gọi TỪNG cổng bằng `run_gate`, KHÔNG dùng `run_chain`. `run_chain` dừng
        # ở cổng `fail` đầu tiên, đúng cho một lượt review SDLC (gate 2 chỉ có
        # nghĩa khi gate 1 đã qua). Một lượt analyze repo thì khác: nó không có
        # tiêu chí nghiệm thu, không có PR diff, không có quan sát sau ship — nên
        # `run_chain` sẽ chặn ngay ở cổng 1 và cổng `grid` (cổng DUY NHẤT có dữ
        # liệu thật ở đây) không bao giờ chạy. Chạy rời từng cổng cho ra bức tranh
        # thật: một cổng chấm được, bốn cổng từ chối vì THIẾU TẠO TÁC.
        #
        # Bốn cổng đỏ đó KHÔNG phải hỏng — chúng là bài học. `refuse()` đặt
        # `denominator=0`, và UI có luật cứng "mẫu số 0 ⇒ ĐỎ bất kể verdict":
        # "chưa soi cái nào" phải trông khác "đã soi và sạch". Một lượt analyze
        # chỉ trả lời được câu hỏi của cổng `grid`; nói thẳng ra bốn câu còn lại
        # chưa ai trả lời thì trung thực hơn là giấu cả năm.
        gate_verdicts: list[GateVerdict] = []
        try:
            gate_cfg = load_gates_config()
            gate_ctx = GateContext(
                config=gate_cfg,
                wilson_lower=wilson_lower_bound,
                # Chỉ cổng `grid` có tạo tác thật từ lượt chạy này. Bốn cái còn
                # lại để `None` một cách CÓ Ý — bịa ra một tạo tác rỗng để cổng
                # "pass" là đúng thứ chuỗi cổng sinh ra để chặn.
                grid_verdict=_GridVerdictForGate(
                    risk_band=_worst_band_name(cells),
                    cells_total=len(cells),
                    cells_scored=scoreable,
                    blocking_zones=[
                        zid for zid, z in per_zone.items() if z["w"] >= blocking_w
                    ],
                    min_per_zone={
                        zid: float(v.get("worst_score", 0.0))
                        for zid, v in floor_verdicts.items()
                    },
                    source_file=str(self.cfg.config_dir / "zones.yaml"),
                    source_line=1,
                ),
            )
            for gate_name in GATE_ORDER:
                gate_verdicts.append(run_gate(gate_name, gate_ctx))
        except (CertusError, ConfigError) as exc:
            # Cấu hình cổng hỏng KHÔNG được làm chết lượt phân tích: mọi con số
            # phía trên đã tính xong và vẫn đúng. Nói ra rồi đi tiếp.
            yield self._event(
                "warning", trace_id, code="gate-chain",
                msg=f"không chạy được chuỗi 5 cổng: {exc}",
            )
        for gv in gate_verdicts:
            yield self._event("gate", trace_id, **gv.model_dump(mode="json"))

        # Bước 8 khai đúng thứ nó đo được: cổng có chặn không. `verdict` cuối cùng
        # còn phụ thuộc "có claim nào ra không" — đó là kết quả của bước 9, không
        # phải của cổng, nên nó thuộc về `response` chứ không thuộc payload này.
        yield self._step(
            trace_id, "run_gates",
            zones=len(floor_verdicts),
            blocking_failures=len(blocking_failures),
            blocked=blocked,
            chain_gates=len(gate_verdicts),
            chain_refused=sum(1 for g in gate_verdicts if g.denominator == 0),
        )

        # ── giai đoạn DIỄN GIẢI: mô hình ĐỌC số, code đã TÍNH xong ──────────
        # Đây là chỗ DUY NHẤT tầng agent chạm pipeline. Khối này từng bị bỏ
        # trống (claims=[], gates=[], verdict="inconclusive"), nên mọi lỗi sống
        # ở đường LLM→claim (confabulation, truncation, nhãn-từ-tool, tất định,
        # cá nhân hoá) không có đường nào biểu hiện. Lỗi ở bước này KHÔNG làm
        # hỏng phần số: coverage vẫn ra, chỉ phần diễn giải khuyết kèm cảnh báo.
        yield self._step(trace_id, "explain", "running")
        nonce = _analyze_nonce(req)
        kb_context = build_context(req.question)
        with PersonaStore(settings=self.cfg) as pstore:
            persona = pstore.persona_block(req.user_id)
        prompt = render_prompt(
            "analyze",
            QUESTION=req.question,
            KB_CONTEXT=kb_context or "(không đoạn KB nào khớp câu hỏi)",
            ARTIFACTS=_format_artifacts(coverage),
            PERSONA=persona or "(chưa có ngữ cảnh cá nhân hoá cho người dùng này)",
            NONCE=nonce,
        )
        system = load_prompt("system")
        # KHÔNG truyền tools vào lượt gọi này — CÓ CHỦ ĐÍCH. Bước diễn giải là
        # single-shot để cassette tất định (1000 sinh viên replay đồng thời, một
        # khoá ổn định cho mỗi (repo, câu hỏi)). Model THẬT được cấp tool sẽ dừng
        # ở `stop_reason=tool_use` chờ kết quả rồi mới nói tiếp — mà luồng này
        # không có vòng lặp tool, nên nó dừng với text RỖNG và không claim nào ra.
        # Prompt vẫn khung tool về mặt khái niệm (bug "only a tool promotes a
        # claim" nằm ở chỗ model TỰ dán nhãn OBSERVED không có tool nào phong),
        # và có sẵn nhánh "nếu tool không khả dụng thì tự tính" — nên model tính
        # trực tiếp rồi trả đúng một object JSON như phần 'Định dạng trả lời' đòi.

        claims: list[Claim] = []
        llm_warnings: list[str] = []
        span = tracing.llm_span("analyze.explain")
        client = LLMClient(self.cfg)
        # Token phải chảy TRONG lúc mô hình viết, không dồn ra sau. Bản cũ `await`
        # cho xong `complete()` rồi mới lặp `resp.chunks` — đo trên một lượt live
        # thật: 57 giây, trong đó ~50 giây im lặng tuyệt đối rồi mọi token đến cùng
        # lúc. Với người đang nhìn, im lặng 50 giây không phân biệt được với đã
        # treo; endpoint là SSE nhưng phần tốn thời gian nhất của nó không stream.
        #
        # `complete()` là một `await` còn ta cần phát giữa chừng, nên hàng đợi nối
        # hai nhịp: lượt gọi chạy như một task, `on_chunk` đẩy vào queue, vòng dưới
        # rút ra và phát tiếp. Cùng cơ chế đã dùng ở `ChatSession.run`.
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _push(chunk: str) -> None:
            await queue.put(chunk)

        async def _ask() -> LLMResponse:
            try:
                return await client.complete(
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    cassette_hint="analyze",
                    # Mồi `{` để ép mọi model (kể cả Haiku yếu) tiếp nối thành đúng
                    # object JSON như "Định dạng trả lời" đòi, thay vì đáp văn xuôi
                    # rồi rớt về cảnh báo "không đọc được câu trả lời". Chỉ tác động
                    # đường API thật; mock/cassette của lớp không đổi khoá.
                    prefill="{",
                    on_chunk=_push,
                )
            finally:
                await queue.put(None)  # sentinel: hết chữ, dù xong hay lỗi

        task = asyncio.create_task(_ask())
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield self._event("token", trace_id, text=chunk)

        try:
            resp = await task
            span.finish(
                status="ok", from_cassette=resp.from_cassette,
                model=resp.model, stop_reason=resp.stop_reason,
                tool_uses=len(resp.tool_uses),
            )
            parsed = extract_claims_json(resp.text)
            if str(parsed.get("nonce")) != nonce:
                # Nonce là cửa chống trả-lời-lạc: câu trả lời không chép đúng
                # nonce có thể là của một prompt khác (hoặc bị bơm), không đọc.
                llm_warnings.append(
                    "câu trả lời của mô hình thiếu hoặc sai nonce — bỏ không đọc"
                )
            else:
                # parse_claims dựng bằng model_construct (bỏ validator — đó là
                # bug nhãn-từ-tool). Pipeline TUYỆT ĐỐI không được sập vì một
                # câu trả lời dị dạng: validate lại từng claim, cái nào validator
                # của chính hệ từ chối thì loại kèm cảnh báo (chính sự bất nhất
                # "parser nhận, validator chối" là thứ tầng B cần phơi), cái nào
                # hợp lệ — kể cả OBSERVED không do tool phong — vẫn tới output.
                for c in parse_claims(parsed):
                    try:
                        Claim.model_validate(c.model_dump())
                    except ValidationError as exc:
                        detail = exc.errors()[0].get("msg", "") if exc.errors() else ""
                        llm_warnings.append(
                            f"claim {c.id!r} dị dạng, không hiển thị: {detail}"
                        )
                        continue
                    claims.append(c)
        except CassetteMissError:
            span.finish(status="error", error="cassette_miss")
            llm_warnings.append(
                "chưa có cassette cho bước diễn giải ở repo/câu hỏi này; chạy một "
                "lượt `CERTUS_LLM_MODE=record` để sinh, hoặc đặt CERTUS_LLM_MODE=live "
                "kèm khoá API"
            )
        except (ClaimParseError, ConfigError) as exc:
            span.finish(status="error", error=type(exc).__name__)
            llm_warnings.append(f"không đọc được câu trả lời của mô hình: {exc}")
        except ValidationError as exc:
            # `parse_claims` dựng claim từ JSON do MÔ HÌNH viết. Ở cây gốc nó đi
            # đường `model_construct` (bỏ validator) nên kiểu sai lọt qua; sau khi
            # vá bài 06 nó dựng bằng constructor thật, và một câu trả lời dị dạng
            # ném ValidationError NGAY TRONG lời gọi — tức ngoài vòng try nhỏ bên
            # dưới, nên nó thoát ra và giết cả lượt phân tích.
            #
            # Đo được với model thật: `flags` trả về list-of-dict thay vì
            # list-of-str → `1 validation error for Claim / flags.0` → toàn bộ
            # lượt chạy chết, mất luôn mọi con số pipeline đã tính xong ở 8 bước
            # trước. Ca đó nay `_normalize_flags` nắn lại ngay trong parse; nhánh
            # này ở lại làm lưới cho những dị dạng CHƯA gặp (claim tỉ lệ OBSERVED
            # thiếu interval, `anchors` sai khuôn…). Một câu trả lời hỏng của mô
            # hình KHÔNG được phép xoá một phép đo đã có: nói ra rồi đi tiếp,
            # đúng như ba nhánh except kia.
            span.finish(status="error", error="ValidationError")
            detail = exc.errors()[0].get("msg", "") if exc.errors() else str(exc)
            loc = ".".join(str(x) for x in (exc.errors()[0].get("loc") or ())) if exc.errors() else ""
            llm_warnings.append(
                "mô hình trả claim sai kiểu, bỏ toàn bộ phần diễn giải"
                + (f" ({loc}: {detail})" if loc or detail else "")
                + " — mọi con số phía trên vẫn do pipeline tính độc lập và vẫn đúng."
            )
        tracing.emit(span)
        yield self._event("span", trace_id, span=span.to_row().to_sse())
        for c in claims:
            yield self._event("claim", trace_id, claim=c.model_dump(mode="json"))

        # Phán quyết cuối gộp HAI nguồn: cổng (bước 8) và việc bước 9 có ra được
        # claim nào không. `blocked` thắng — một lượt bị cổng chặn thì dù mô hình
        # nói gì cũng không thành "pass".
        verdict = "blocked" if blocked else ("pass" if claims else "inconclusive")

        # Cảnh báo giữ tệp phải NÊU RÕ tệp nào — "1 tệp bị giữ lại" không cho người
        # đọc biết gì để đối chiếu với danh sách "đã gửi". `held` là {đường-dẫn:
        # lý-do}; liệt kê đường dẫn (kèm lý do khi đủ chỗ).
        held_warning = (
            f"{len(held)} tệp bị giữ lại theo chính sách dữ liệu: "
            + "; ".join(f"{p} ({r})" for p, r in sorted(held.items()))
            if held
            else None
        )
        response = AnalyzeResponse(
            run_id=trace_id,
            trace_id=trace_id,
            target=req.target or req.upload_id or str(req.local_path),
            coverage=coverage,
            claims=[ClaimOut(claim=c, supported_by=c.evidence_ids) for c in claims],
            # `gate_verdicts` là ĐÚNG danh sách vừa phát ra trên dòng SSE ở bước
            # 8. Trước bản này chỗ này để `[]` cứng, nên cùng MỘT lượt chạy trả
            # hai câu trả lời khác nhau tuỳ đường vào: người xem giao diện thấy
            # năm cổng, người gọi `/api/analyze` thấy không cổng nào. Trường
            # `gates` vẫn được khai trong `AnalyzeResponse`, nên bên gọi có mọi
            # lý do để tin rằng rỗng nghĩa là "không có cổng nào chạy".
            gates=gate_verdicts,
            verdict=verdict,
            files_sent_to_model=sent,
            warnings=([held_warning] if held_warning else []) + llm_warnings,
        )
        # Cảnh báo phải ra thành sự kiện riêng, không nằm lẫn trong response —
        # hợp đồng bắt mỗi cảnh báo hiện thành một DÒNG CHỮ trên UI, và một
        # trường trong JSON thì không có gì buộc UI phải hiển thị nó.
        for flag in (line_rate.flags if line_rate else []) + grid_rate.flags:
            yield self._event(
                "warning", trace_id, code=flag,
                msg=_WARNING_TEXT.get(flag, flag),
            )
        # Hai NGUỒN cảnh báo khác hẳn nhau, KHÔNG gộp chung mã: giữ tệp là chuyện
        # chính sách dữ liệu; còn "mô hình trả sai định dạng / nonce lệch / claim
        # dị dạng" là chuyện của bước diễn giải. Gắn `data-policy` cho nhóm sau thì
        # UI in nhầm tiêu đề "đã giữ tệp" lên một lỗi output của mô hình.
        if held_warning:
            yield self._event("warning", trace_id, code="data-policy", msg=held_warning)
        for w in llm_warnings:
            yield self._event("warning", trace_id, code="llm-output", msg=w)

        yield self._step(trace_id, "explain", response=response.model_dump(mode="json"))


async def analyze(req: AnalyzeRequest, settings: Settings | None = None) -> PipelineResult:
    """Chạy hết luồng và gom lại thành một kết quả — dùng cho CLI và test."""
    pipe = Pipeline(settings)
    events: list[StreamEvent] = []
    response: AnalyzeResponse | None = None
    async for ev in pipe.run(req):
        events.append(ev)
        if (
            ev.kind == "step"
            and ev.payload.get("name") == "explain"
            and "response" in ev.payload
        ):
            # Bước `explain` phát hai lần: `status="running"` (chưa có response)
            # rồi bước đóng kèm `response`. Chỉ đọc cái sau.
            response = AnalyzeResponse.model_validate(ev.payload["response"])
        if ev.kind == "error":
            raise CertusError(ev.payload["msg"])
    if response is None:
        raise CertusError("luồng kết thúc mà không sinh ra kết quả nào")
    return PipelineResult(response=response, events=events)


#: Dòng `KEY=value` mà một bộ kiểm in ra khi nó TỪ CHỐI chạy vì thiếu biến môi
#: trường. Tên biến kiểu shell (hoa, gạch dưới), giá trị là phần còn lại tới hết
#: dòng hoặc tới khoảng trắng — đủ để bắt cả URL có `://`, `@`, `:cổng`, `/db`.
_ENV_HINT_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})=(\S+)")

#: Biến KHÔNG bao giờ gợi ý dán lại, dù có xuất hiện trong log: chúng là biến
#: của MÁY CHỦ, và bảo người dùng đặt lại `PATH` hay `HOME` cho repo của họ là
#: một lời khuyên vừa vô nghĩa vừa nguy hiểm.
_ENV_HINT_DENY = frozenset({"PATH", "HOME", "PWD", "TMPDIR", "USER", "SHELL", "LANG"})


def _suggest_env_fix(tail: str) -> str:
    """Trích những dòng `KEY=value` mà chính repo đích đã in ra trong log lỗi.

    Vì sao đáng có một hàm riêng thay vì để người dùng tự đọc log: khi một repo
    từ chối chạy vì thiếu biến môi trường, nó gần như luôn in ra ĐÚNG dòng cần
    đặt. Đo trên `vsf/document-intake`: conftest chặn ở cổng DB rồi in nguyên
    văn `Set VSF_DATABASE_URL=postgresql://vsf:vsf@localhost:5433/vsf_aio`.
    Câu trả lời nằm sẵn trong log — nhưng nó là dòng thứ mười mấy của một khối
    chẩn đoán dài, dưới một tiêu đề đỏ ghi "sai cách gọi pytest (usage error)".

    Người đọc dừng ở tiêu đề đó, và tiêu đề đó ĐÚNG về mặt kỹ thuật (pytest quả
    thật trả exit 4) mà SAI về mặt hành động: nó nghe như lỗi của CERTUS gọi sai
    lệnh, trong khi việc cần làm là dán một dòng vào ô 'biến môi trường'. Kéo
    dòng đó lên đầu là biến một ngõ cụt thành một bước tiếp theo.

    Không trích được gì thì trả lời khuyên chung — KHÔNG bịa ra một tên biến.
    """
    seen: dict[str, str] = {}
    for name, value in _ENV_HINT_RE.findall(tail or ""):
        if name not in _ENV_HINT_DENY and name not in seen:
            seen[name] = value.rstrip(".,;:'\"`)")
    if not seen:
        return (
            "Sửa được không: đọc đuôi log dưới đây. Repo đòi một biến môi trường "
            "hoặc một dịch vụ nào đó thì khai ở ô 'Lệnh' / 'Biến môi trường' "
            "trong khối 'Cách chạy bộ kiểm' (cột phải) rồi chạy lại.\n"
        )
    lines = "\n".join(f"  {k}={v}" for k, v in seen.items())
    return (
        "CÁCH SỬA — chính repo đích đã in ra biến nó cần. Dán nguyên văn "
        f"{'dòng' if len(seen) == 1 else 'các dòng'} dưới đây vào ô 'Biến môi "
        "trường' (khối 'Cách chạy bộ kiểm', cột phải) rồi chạy lại:\n"
        f"{lines}\n"
        "Kiểm trước khi chạy lại: dịch vụ ở địa chỉ đó phải đang chạy thật.\n"
    )


def run_target_suite(
    root: Path,
    plan: ProvisionPlan | None = None,
    extra_env: Mapping[str, str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, set[str], tuple[int, int]]:
    """Chạy bộ kiểm của repo đích và đọc lại phần nó đã chạm.

    Đi qua `core/exec/runner` (gián tiếp qua `provision.run_suite`) chứ không
    gọi `subprocess` thẳng: đó là chỗ duy nhất có allowlist và có ghi sổ bằng
    chứng. Một lối chạy thứ hai, dù chỉ để tiện, là một lối vòng qua cả hai.

    `plan` None ⇒ tự dò (giữ nguyên hành vi cũ cho mọi người gọi cũ).
    """
    if plan is None:
        plan = detect_plan(root)
    outcome = run_suite(root, plan, extra_env=extra_env, on_line=on_line)
    covered: set[str] = set()
    lines_hit = 0
    lines_total = 0
    data_file = root / ".coverage"
    if data_file.exists():
        try:
            # Dùng `analysis2()` của chính coverage.py chứ không tự đếm câu lệnh:
            # nó biết dòng nào CHẠY ĐƯỢC, dòng nào bị `# pragma: no cover`, dòng
            # nào chỉ là tiếp nối của câu lệnh trước. Bản tự đếm bằng AST của tôi
            # từng cho ra 444/444 = 100% vì nhánh parse nổ rồi rơi về
            # `total = hit` — mẫu số bằng tử số thì tỉ lệ luôn đẹp.
            from coverage import Coverage

            cov = Coverage(data_file=str(data_file))
            cov.load()
            for measured in sorted(cov.get_data().measured_files()):
                name = Path(measured).stem
                if name.startswith("test_") or name == "conftest":
                    # Bài kiểm không thuộc mẫu số của độ phủ: đo xem bài kiểm có
                    # tự chạy hết chính nó không thì luôn ra gần 100%.
                    continue
                _fn, statements, _excluded, missing, _fmt = cov.analysis2(measured)
                lines_total += len(statements)
                lines_hit += len(statements) - len(missing)
                covered.add(name)
                for line_no in set(statements) - set(missing):
                    covered.add(f"{name}:{line_no}")
        except Exception:  # noqa: BLE001 — thiếu coverage không được làm chết luồng
            lines_hit = lines_total = 0

    # Tên hàm cấp module cũng được coi là "đã chạm", để `code_path` tra được
    # bằng tên hàm thay vì bằng số dòng.
    for py in root.rglob("*.py"):
        if is_vendor_path(py, root) or py.stem.startswith("test_"):
            continue
        try:
            import ast as _ast

            for node in _ast.walk(_ast.parse(py.read_text(encoding="utf-8"))):
                if isinstance(node, _ast.FunctionDef) and py.stem in covered:
                    covered.add(node.name)
        except (SyntaxError, UnicodeDecodeError):
            continue
    # Không bao giờ để hit > total: nếu xảy ra thì mẫu số sai, và một tỉ lệ
    # trên 100% là dấu hiệu đầu tiên nhìn thấy được của chuyện đó.
    lines_total = max(lines_total, lines_hit)

    # ── bộ kiểm KHÔNG chạy được ⇒ dừng, không đo tiếp ─────────────────────────
    # Exit code khác 0 mà KHÔNG thu được dòng phủ nào nghĩa là pytest chưa từng
    # chạy tới phần thân: collect fail, thiếu dependency, import nổ. Trả
    # `(exit, set(), (0,0))` rồi đi tiếp thì mọi ô rơi `coverage_mismatch` và UI
    # hiện "chưa ai canh" — người đọc hiểu thành "repo này không có test", trong
    # khi sự thật là "CERTUS không chạy được test của repo này". Đó là biến
    # "tôi không đo được" thành "tôi đã đo và kết quả tệ".
    #
    # Test ĐỎ thì khác: pytest chạy thật, có dòng phủ, exit khác 0 là một quan
    # sát HỢP LỆ (`known_failure` ở project.py hàng 3). Nên điều kiện là exit
    # khác 0 VÀ không thu được gì, không phải exit khác 0 đơn thuần.
    # Sandbox CẮT NGANG (hết giờ, ngoài allowlist) không phải một phép đo, kể
    # cả khi lượt chạy dở đã kịp ghi `.coverage`: con số đó là của một bộ kiểm
    # chạy được 8% rồi bị giết. Báo "đo xong" ở đây là lỗi tệ nhất trong tệp
    # này — nó cho ra một bảng grid trông hoàn chỉnh dựng trên số liệu cụt.
    if not outcome.ran:
        raise SuiteRunFailed(
            f"lượt chạy bộ kiểm bị cắt ngang: {outcome.block_reason or 'không rõ lý do'}. "
            "Đây KHÔNG phải một phép đo — phần đã chạy được không đại diện cho cả "
            "bộ kiểm.\n"
            f"Môi trường: {outcome.plan.kind} — {outcome.plan.reason}\n"
            f"Lệnh: {' '.join(outcome.plan.argv)}\n"
            f"Đuôi log:\n{outcome.output_tail}"
        )
    # Exit code của pytest nói RẤT rõ chuyện gì đã xảy ra, và ba giá trị dưới đây
    # nghĩa là bộ kiểm CHƯA TỪNG CHẠY — không phải "chạy rồi và đỏ":
    #
    #   2 = bị ngắt giữa chừng   3 = lỗi nội bộ
    #   4 = sai cách gọi (usage) 5 = không gom được test nào
    #
    # Chỉ exit 1 là "đã chạy, có test đỏ" — một quan sát HỢP LỆ (`known_failure`).
    #
    # Vì sao điều kiện cũ (`exit != 0 và không thu được gì`) không đủ: nó tin rằng
    # suite không chạy thì `.coverage` sẽ rỗng. Sai. Đo thật trên
    # `vsf/document-intake`: `conftest.py` có guard chặn chạy nhầm DB production và
    # gọi `sys.exit` ngay khi nạp. pytest trả exit 4, KHÔNG một test nào chạy —
    # nhưng `coverage` đã kịp ghi 7 tệp (`conftest.py` và các `__init__.py` nạp
    # trước lúc thoát). `covered` không rỗng nên nhánh chặn không cắn, và CERTUS
    # in ra `line_coverage 93/100 = 93.0%`.
    #
    # 93% dựng trên một bộ kiểm chưa từng chạy là lỗi tệ nhất mà công cụ này có
    # thể mắc: nó không sai một chút, nó sai theo hướng làm người đọc yên tâm.
    # Đúng cái CERTUS tồn tại để chống. Nên chặn theo Ý NGHĨA của exit code, chứ
    # không theo việc có nhặt được byte nào hay không.
    SUITE_NEVER_RAN = {2: "bị ngắt giữa chừng", 3: "lỗi nội bộ của pytest",
                       4: "sai cách gọi pytest (usage error)",
                       5: "không gom được test nào"}
    if outcome.exit_code in SUITE_NEVER_RAN:
        raise SuiteRunFailed(
            f"bộ kiểm của repo đích chưa từng chạy: pytest thoát với exit="
            f"{outcome.exit_code} ({SUITE_NEVER_RAN[outcome.exit_code]}). Chỉ exit=1 "
            "mới nghĩa là 'đã chạy và có test đỏ'.\n"
            f"Đã nhặt được {len(covered)} ký hiệu từ `.coverage`, nhưng đó là phần "
            "Python nạp TRƯỚC khi bộ kiểm dừng — không phải một phép đo. Báo một tỉ "
            "lệ ở đây là biến 'tôi không đo được' thành 'tôi đã đo và kết quả tốt'.\n"
            f"Môi trường đã dùng: {outcome.plan.kind} — {outcome.plan.reason}\n"
            f"Lệnh: {' '.join(outcome.plan.argv)}\n"
            f"{_suggest_env_fix(outcome.output_tail)}"
            f"Đuôi log:\n{outcome.output_tail}"
        )
    if outcome.exit_code != 0 and not covered:
        raise SuiteRunFailed(
            f"bộ kiểm của repo đích không chạy được (exit={outcome.exit_code}, "
            "không thu được dòng phủ nào) — thường là thiếu dependency hoặc import "
            "lỗi lúc collect. Chưa đo được gì thì mọi con số phủ phía sau đều vô "
            f"nghĩa.\nMôi trường đã dùng: {outcome.plan.kind} — {outcome.plan.reason}\n"
            f"Lệnh: {' '.join(outcome.plan.argv)}\n"
            f"Đuôi log:\n{outcome.output_tail}"
        )
    return outcome.exit_code, covered, (lines_hit, lines_total)


def infer_entry_symbol(root: Path, cov_suite: set[str]) -> str | None:
    """Ký hiệu để neo `code_path` — suy từ REPO, không phải một hằng số.

    `code_path` là thứ `project.py` hỏi "ô này có ai chạm không". Ghim cứng một
    cái tên (`"checkout"`) làm mọi repo không có ký hiệu ấy rơi `coverage_mismatch`
    toàn bảng — full unknown kể cả khi bộ kiểm chạy hoàn hảo. Con số sai đó im
    lặng, và nó tệ hơn không có con số.

    Luật chọn, theo thứ tự:
    1. `checkout` nếu repo có — giữ bất biến cho repo mẫu (cassette + golden).
    2. Hàm cấp module ĐÃ ĐƯỢC PHỦ, nhiều dòng nhất — hàm to nhất mà bộ kiểm thật
       sự chạm là cái neo được vào bằng chứng.
    3. `None` nếu không suy được, để nơi gọi khai thẳng thay vì bịa một cái tên.
    """
    if "checkout" in cov_suite:
        return "checkout"
    import ast as _ast

    best: tuple[int, str] | None = None
    for py in sorted(root.rglob("*.py")):
        if is_vendor_path(py, root) or py.stem.startswith("test_") or py.stem == "conftest":
            continue
        try:
            tree = _ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in tree.body:  # cấp module thôi — khớp cách covered được nạp
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            if node.name not in cov_suite:
                continue
            size = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno
            # Hoà số dòng thì lấy tên NHỎ hơn theo thứ tự chữ — để hai lượt chạy
            # trên cùng một repo luôn cho cùng một ký hiệu.
            if best is None or size > best[0] or (size == best[0] and node.name < best[1]):
                best = (size, node.name)
    return best[1] if best else None
