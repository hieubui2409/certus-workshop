"""Kiểu dữ liệu dùng chung của CERTUS.

Đây là chỗ ở DUY NHẤT của các enum dưới đây. Module khác import từ đây,
không tự khai lại — một enum bị khai hai nơi là cách kinh điển để hai nửa
hệ thống trôi khỏi nhau mà không ai thấy.

Neo tài liệu:
  - Hệ 4 nhãn: harness/rules/verification-mechanism.md:28-33
  - Band + source="projected": tot-grid-coverage/harness/data/schemas/grid-state.schema.json
  - evidence_tier: qa-gate-chain/build/design/architecture.md:132-134
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Label(StrEnum):
    """Nhãn bằng chứng của một claim.

    Nguyên tắc nền: "The label IS the grammar: a claim's wording must never
    out-run its evidence tier."
    """

    OBSERVED = "OBSERVED"  # đã chạy/đọc/đo trực tiếp, và chưa có gì đổi từ đó
    DERIVED = "DERIVED"  # suy ra từ OBSERVED bằng một cơ chế phát biểu được
    PRIOR = "PRIOR"  # kiến thức huấn luyện, có thể đã cũ
    ASSUMED = "ASSUMED"  # chưa kiểm chứng nhưng kết luận đang cần tới


#: "Không đủ tư cách mang bất kỳ nhãn nào" — tầng meta, KHÔNG cùng trục với Label.
#: Đây là một phán quyết HỢP LỆ, không phải một thất bại.
UNVERIFIED = "UNVERIFIED"


class Band(StrEnum):
    """Mức phủ của một grid cell. Luôn là kết quả suy diễn, không bao giờ do
    model chọn."""

    HIGH = "high"
    MED = "med"
    LOW = "low"
    STUB = "stub"
    NA = "N/A"
    UNKNOWN = "unknown"


class EvidenceTier(StrEnum):
    """Mức bằng chứng một gate dựa vào.

    Cố ý KHÔNG có "asserted" — nói suông bị cấm tuyệt đối làm cơ sở kết luận.
    """

    EXECUTED = "executed"
    RETRIEVED = "retrieved"
    DERIVED = "derived"


class GateName(StrEnum):
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    GRID = "grid"
    EXECUTION = "execution"
    OUTCOME = "outcome"


IntervalMethod = Literal["wilson", "wilson-cc", "clopper-pearson", "jeffreys"]
ClusterRoute = Literal["icc", "icc-upper", "cluster-floor"]


class Interval(BaseModel):
    """Khoảng tin cậy cho một tỉ lệ.

    `saturated` không có nghĩa là "hẹp" — nó có nghĩa là interval đã TRÀN ra
    ngoài [0,1] rồi bị cắt về. Một judge tệ cho ra interval trông hẹp nhất
    bảng đúng vì lý do này, nên cờ phải đi kèm số.
    """

    lower: float
    upper: float
    conf: float = 0.95
    method: IntervalMethod = "wilson"
    n: int
    k: int
    n_eff: float | None = None
    route: ClusterRoute | None = None
    saturated: bool = False

    @property
    def width(self) -> float:
        return self.upper - self.lower


class Anchor(BaseModel):
    """Neo bằng chứng. Claim không có neo là UNVERIFIABLE, và downstream coi
    nó như không tồn tại."""

    kind: Literal["file_line", "command", "artifact"]
    ref: str  # "src/cart.py:42" | "pytest -q" | "sha256:abc..."
    exit_code: int | None = None


class Claim(BaseModel):
    """Một câu CERTUS nói về code của bạn."""

    id: str
    text: str
    label: Label
    k: int | None = None
    n: int | None = None
    interval: Interval | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    is_rate: bool = False
    mechanism: str | None = None  # bắt buộc nêu ra thì mới được DERIVED

    @model_validator(mode="after")
    def _rate_claims_need_interval(self) -> Claim:
        """Khi claim là một TỈ LỆ, [OBSERVED] chỉ hợp lệ kèm k/n và interval.

        Một câu "[OBSERVED] độ chính xác 92%" trơ trọi là claim DỊ DẠNG:
        nhãn trả lời "có chạy thật không", nó không trả lời "chạy bao nhiêu lần".
        3/3 và 300/300 mang cùng nhãn nhưng một cái đảm bảo 43.9%, cái kia 98.9%.
        """
        if self.is_rate and self.label is Label.OBSERVED:
            if self.k is None or self.n is None or self.interval is None:
                raise ValueError(
                    f"malformed claim {self.id!r}: claim tỉ lệ gắn nhãn OBSERVED "
                    f"mà thiếu k/n hoặc interval"
                )
        return self

    @model_validator(mode="after")
    def _observed_needs_anchor(self) -> Claim:
        """Verification invariant #1: phải có neo (SHA, file:line, hoặc output
        lệnh thật). Không neo thì không có tư cách OBSERVED."""
        if self.label is Label.OBSERVED and not self.anchors:
            raise ValueError(f"claim {self.id!r}: OBSERVED mà không có anchor")
        return self


class Cell(BaseModel):
    """Một ô của grid — một phép gán đầy đủ cho một t-subset của axes."""

    id: str  # cell:<axis>=<v>|<axis>=<v> — canonical, không tự đặt
    axes: dict[str, str]
    zone_id: str
    zone_w: float
    band: Band
    source: Literal["projected"] = "projected"
    flags: list[str] = Field(default_factory=list)
    evidence_id: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """Một phát hiện của gate. `file` và `line` là BẮT BUỘC — finding không
    neo được vào chỗ nào trong code thì downstream không xử lý được."""

    rule_id: str
    severity: Literal["info", "warn", "error"]
    file: str
    line: int
    finding: str


class GateVerdict(BaseModel):
    """Phán quyết của một cổng.

    `verdict` chỉ có MỘT hệ {pass, fail}. Cố ý không trộn hệ review kế hoạch
    (approve/block/request-revision) vào đây — trộn hai hệ trong một type là
    bẫy trùng-từ-khác-nghĩa đã có tiền lệ.
    """

    gate: GateName
    verdict: Literal["pass", "fail"]
    evidence_tier: EvidenceTier | None = None
    findings: list[Finding] = Field(default_factory=list)
    compare_op: str = ">="  # dấu so sánh nằm trong hợp đồng, không để ngầm
    denominator: int = 0  # symbols_scanned — 0 nghĩa là ĐỎ, không phải xanh
    blocked: bool = False
    skipped: bool = False
    reason: str | None = None


class LedgerRecord(BaseModel):
    """Một dòng của sổ bằng chứng append-only."""

    claim_id: str
    command: str
    exit_code: int | None
    output_sha256: str
    verdict: Literal["executed-pass", "executed-fail", "UNVERIFIED"]
    prev_hash: str
    self_hash: str
    ts: str
    actor: str | None = None
