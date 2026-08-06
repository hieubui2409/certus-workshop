"""Hình dạng dữ liệu đi qua dây HTTP.

Tách khỏi `contracts/types.py` có chủ đích: `contracts` là ngôn ngữ nội bộ giữa
các tầng và được phép đổi; phần dưới đây là thứ frontend và các eval nhìn thấy,
nên đổi nó là đổi hợp đồng công khai.

Một luật chi phối cả tệp: **mọi tỉ lệ ra tới UI phải mang theo mẫu số.** Một
con số phần trăm không có `n` bên cạnh thì người đọc không có cách nào biết nó
đến từ 3 quan sát hay 300.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.types import (
    Band,
    Cell,
    Claim,
    GateVerdict,
    Interval,
)

# --------------------------------------------------------------------------
# Yêu cầu
# --------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Yêu cầu phân tích một repo.

    `target` trỏ tới một repo mẫu đi kèm; `upload_id` trỏ tới thứ người dùng
    vừa tải lên. Đúng một trong hai, không cả hai — nhập nhèm nguồn đầu vào là
    chỗ đầu tiên một biên tin cậy bị xoá nhoà.
    """

    target: str | None = None
    upload_id: str | None = None
    question: str = "Bộ kiểm thử của repo này phủ tới đâu?"
    user_id: str = "guest"
    project_id: str | None = None


class UploadAck(BaseModel):
    upload_id: str
    files_accepted: int
    files_rejected: int
    rejected_reasons: dict[str, str] = Field(default_factory=dict)
    bytes_total: int


# --------------------------------------------------------------------------
# Số liệu
# --------------------------------------------------------------------------


class RateOut(BaseModel):
    """Một tỉ lệ ra tới UI.

    Ba trường `k`, `n`, `interval` đi cùng nhau hoặc không đi. Đây là chỗ luật
    "claim tỉ lệ phải có mẫu số và khoảng" được cưỡng chế tại biên HTTP, không
    phải chỉ trong tài liệu.
    """

    name: str
    k: int
    n: int
    point: float
    interval: Interval
    flags: list[str] = Field(default_factory=list)


class ZoneOut(BaseModel):
    zone_id: str
    weight: float
    score: float
    cells_total: int
    cells_scoreable: int
    min_cell_band: Band | None = None


class CoverageOut(BaseModel):
    """Ba tầng mẫu số, cạnh nhau, không gộp.

    `risk_weighted` là số CHẨN ĐOÁN — nó nói bức tranh chung nghiêng về đâu.
    `per_zone` là thứ cổng thật đọc. Hai con số này trả lời hai câu hỏi khác
    nhau, nên tệp này cố ý không có trường nào là trung bình của cả hai.
    """

    line: RateOut | None = None
    mutation: RateOut | None = None
    grid: RateOut | None = None

    risk_weighted: dict[str, Any]
    per_zone: list[ZoneOut]

    cells: list[Cell] = Field(default_factory=list)
    cells_total: int = 0
    cells_na: int = 0
    cells_unknown: int = 0

    # Con số duy nhất được phép đứng một mình, vì nó là điểm tổng hợp mà
    # người dùng chờ đợi thấy ngay ở đầu trang.
    confidence: float = 0.0


class ClaimOut(BaseModel):
    claim: Claim
    supported_by: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    run_id: str
    trace_id: str
    target: str
    coverage: CoverageOut
    claims: list[ClaimOut] = Field(default_factory=list)
    gates: list[GateVerdict] = Field(default_factory=list)
    verdict: Literal["pass", "blocked", "inconclusive"] = "inconclusive"
    files_sent_to_model: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Giao thức SSE
# --------------------------------------------------------------------------


class StreamEvent(BaseModel):
    """Một sự kiện trên dòng SSE.

    `seq` tăng đơn điệu trong một run để frontend phát hiện được sự kiện rơi.
    Một dòng stream không đánh số thì mất gói trông y hệt như đang xử lý chậm.
    """

    seq: int
    #: ĐÚNG 10 loại, khoá bởi SDD 00 §5. Frontend đã dựng theo danh sách này;
    #: thêm một loại thứ 11 ở backend nghĩa là phát ra thứ không ai hiển thị.
    kind: Literal[
        "step",
        "log",
        "claim",
        "cell",
        "gate",
        "token",
        "span",
        "warning",
        "done",
        "error",
    ]
    trace_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

    def wire_data(self) -> dict[str, Any]:
        """Phần đi vào `data:` của dòng SSE.

        Hợp đồng nói `data` là payload trần (`<Cell JSON>`), không phải phong bì.
        `seq` được cộng thêm vào payload — thêm khoá là thay đổi cộng tính, client
        không biết nó thì bỏ qua; đổi hình dạng phong bì thì không.
        """
        return {**self.payload, "seq": self.seq, "trace_id": self.trace_id}


class ErrorOut(BaseModel):
    """Lỗi trả về. `detail` phải là câu đọc được, không phải mã.

    Một thông báo lỗi mà người đọc phải tra bảng mới hiểu thì trong thực tế
    không ai đọc — họ thử lại cho tới khi nó biến mất.
    """

    error: str
    detail: str
    trace_id: str | None = None
    hint: str | None = None
