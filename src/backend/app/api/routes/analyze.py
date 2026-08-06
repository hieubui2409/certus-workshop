"""Chạy phân tích, phát kết quả qua SSE."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import AnalyzeRequest, AnalyzeResponse
from app.api.deps import needs
from app.orchestrator.pipeline import Pipeline, analyze as run_analyze
from app.settings import settings

router = APIRouter(prefix="/api", tags=["analyze"])

#: Kết quả gần nhất theo run_id. Đủ cho workshop chạy một máy; nói rõ ở đây để
#: không ai đọc nhầm nó là một tầng lưu trữ.
_RUNS: dict[str, AnalyzeResponse] = {}


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_sync(req: AnalyzeRequest, principal=Depends(needs("probe:run"))):
    """Chạy đồng bộ, trả một lần. Dùng cho CLI, test và eval."""
    result = await run_analyze(req)
    _RUNS[result.response.run_id] = result.response
    return result.response


@router.post("/analyze/stream")
async def analyze_stream(req: AnalyzeRequest, principal=Depends(needs("probe:run"))):
    """Phát tiến trình theo thời gian thực.

    Mỗi sự kiện mang `seq` tăng đơn điệu: mất gói phải phân biệt được với xử lý
    chậm, và không đánh số thì hai thứ đó trông y hệt nhau trên màn hình.
    """
    pipe = Pipeline(settings)

    async def gen():
        async for ev in pipe.run(req):
            # Bước `explain` phát HAI lần: `status="running"` (chưa có response)
            # rồi `status="done"` (có response). Chỉ lần sau mới mang response —
            # thiếu guard này thì lần "running" gây KeyError và sập cả stream.
            if (
                ev.kind == "step"
                and ev.payload.get("name") == "explain"
                and "response" in ev.payload
            ):
                resp = AnalyzeResponse.model_validate(ev.payload["response"])
                _RUNS[resp.run_id] = resp
            yield {"event": ev.kind, "data": json.dumps(ev.wire_data(), ensure_ascii=False)}

    return EventSourceResponse(gen())


@router.get("/coverage/{run_id}")
def coverage(run_id: str, principal=Depends(needs("grid:read"))):
    """Ba tầng mẫu số dưới dạng MẢNG.

    Mảng, không phải object có ba khoá: một object mời người ta thêm khoá thứ
    tư tên `overall`, còn một mảng thì không có chỗ nào để bắt vít cái đó vào.
    """
    resp = _RUNS.get(run_id)
    if resp is None:
        return []
    cov = resp.coverage

    meta = {
        "line": (
            "Ba tầng độ phủ dòng",
            "Dòng nào chưa từng chạy?",
            "coverage.py",
            "mẫu số = số câu lệnh chạy được trong mã nguồn",
        ),
        "mutation": (
            "Điểm đột biến",
            "Bài kiểm có bắt được lỗi không?",
            "mutmut",
            "mẫu số = số đột biến đã sinh trên các dòng bài kiểm đã chạm",
        ),
        "grid": (
            "Độ phủ lưới rủi ro",
            "Còn góc rủi ro nào chưa ai nhìn?",
            "core/grid",
            "mẫu số = số ô t-wise chấm được (đã trừ N/A)",
        ),
    }

    out = []
    for layer_id, value in (("line", cov.line), ("mutation", cov.mutation), ("grid", cov.grid)):
        title, question, source, note = meta[layer_id]
        if value is None:
            # Tầng CHƯA ĐO vẫn phải xuất hiện. Bỏ nó đi làm mảng còn hai phần tử
            # và người đọc kết luận sản phẩm chỉ có hai tầng — "chưa đo" biến
            # thành "không tồn tại", đúng cái nhầm lẫn tệ nhất ở đây.
            out.append(
                {
                    "id": layer_id,
                    "title": title,
                    "question": question,
                    "source": source,
                    "k": 0,
                    "n": 0,
                    "interval": None,
                    "flags": ["not-measured"],
                    "denominator_note": f"CHƯA ĐO — {note}",
                    "evidence_ids": [],
                }
            )
            continue
        row = value.model_dump(mode="json")
        row.update(
            id=layer_id, title=title, question=question, source=source,
            denominator_note=note, evidence_ids=[],
        )
        out.append(row)
    return out
