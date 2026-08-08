"""`/analyze` phải phát token TRONG lúc mô hình viết, và phát bước đúng thứ tự.

Hai lỗi đo được trên một lượt live thật (shopcart, 57.1s):

1. `explain` `await client.complete(...)` cho XONG rồi mới lặp `resp.chunks` phát
   `token`. Tức mọi token đến cùng một lúc, sau ~50 giây im lặng — và với người
   đang nhìn, im lặng 50 giây không phân biệt được với đã treo. Endpoint là SSE
   nhưng phần tốn thời gian nhất của nó không stream.

2. `explain` (bước 9) phát `running` TRƯỚC khi `run_gates` (bước 8) phát `done`,
   nên thanh tiến trình nhảy ngược 9 → 8 → 9.

Cả hai đều không làm sai một con số nào. Chúng làm sai thứ người dùng TIN về
trạng thái hệ thống, mà đó cũng là một loại sai.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.api.schemas import AnalyzeRequest  # noqa: E402
from app.orchestrator.pipeline import Pipeline  # noqa: E402
from app.settings import settings  # noqa: E402


#: Câu hỏi PHẢI là một trong ba câu đã thu cassette cho `shopcart` — khoá cassette
#: băm cả prompt, nên đổi một chữ là miss, và miss thì không có lượt gọi model nào
#: để mà stream. Test này đo THỨ TỰ sự kiện, không đo hành vi lúc miss.
_QUESTION = "Bộ kiểm thử của repo này phủ tới đâu?"


def _events() -> list:
    """Chạy một lượt analyze trên repo mẫu (mock/cassette) và gom sự kiện."""
    pipe = Pipeline(settings)
    req = AnalyzeRequest(target="shopcart", question=_QUESTION)

    async def go():
        return [ev async for ev in pipe.run(req)]

    return asyncio.run(go())


def test_token_den_truoc_khi_explain_ket_thuc():
    """Token phải chảy TRONG bước explain, không dồn ra sau khi nó xong."""
    evs = _events()
    kinds = [e.kind for e in evs]
    assert "token" in kinds, "explain phải phát token"

    # Vị trí sự kiện `step` mang name=explain và có `response` (tức explain xong).
    explain_done = next(
        i for i, e in enumerate(evs)
        if e.kind == "step" and e.payload.get("name") == "explain"
        and "response" in e.payload
    )
    first_token = kinds.index("token")
    assert first_token < explain_done, "token phải đến TRƯỚC lúc explain kết thúc"


def test_run_gates_phat_xong_truoc_khi_explain_bat_dau():
    """Bước 8 phải đóng trước khi bước 9 mở — thanh tiến trình không nhảy ngược."""
    evs = _events()
    steps = [
        (i, e.payload.get("name"), e.payload.get("status"))
        for i, e in enumerate(evs)
        if e.kind == "step"
    ]
    gates_done = next(i for i, n, s in steps if n == "run_gates" and s == "done")
    explain_running = next(i for i, n, s in steps if n == "explain" and s == "running")
    assert gates_done < explain_running, (
        f"run_gates(done)@{gates_done} phải trước explain(running)@{explain_running}"
    )


def test_thu_tu_step_tang_dan_theo_so():
    """Số bước phát ra phải không giảm — nếu giảm thì UI vẽ ngược."""
    evs = _events()
    numbers = [
        e.payload["step"] for e in evs
        if e.kind == "step" and isinstance(e.payload.get("step"), int)
    ]
    assert numbers == sorted(numbers), f"số bước nhảy ngược: {numbers}"
