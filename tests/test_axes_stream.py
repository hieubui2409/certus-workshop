"""`/api/axes/discover` phát tiến trình qua SSE — người xem thấy engine ĐANG nghĩ.

Trước đây endpoint là REST một phát: người dùng bấm, chờ vài giây trong im lặng,
rồi nhận cả bảng. Ở repo thật, "vài giây" là quét hàng nghìn file + một lượt gọi
mô hình — và một thanh chờ không nói gì thì không phân biệt được "đang chạy" với
"đã treo".

Hai luật neo ở đây:

1. **Thứ tự sự kiện phản ánh thứ tự CÔNG VIỆC THẬT.** scan → propose → (llm) →
   admit từng trục → done. Không gom cuối rồi phát một lượt cho giống stream.
2. **Mock KHÔNG giả vờ có mô hình.** Chế độ mặc định của lớp không gọi LLM, nên
   stream phải nói thẳng điều đó bằng một sự kiện `llm_skipped` — chứ không im
   lặng (đọc thành "mô hình không nói gì") và cũng không phát lại token cassette
   như thể đang nghĩ thật.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.main import app  # noqa: E402
from app.settings import settings  # noqa: E402


def _events(body: str) -> list[tuple[str, dict]]:
    """Bóc SSE thô thành [(event, payload)] theo đúng thứ tự đến."""
    out: list[tuple[str, dict]] = []
    kind = None
    for line in body.splitlines():
        if line.startswith("event:"):
            kind = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and kind:
            out.append((kind, json.loads(line.split(":", 1)[1].strip())))
            kind = None
    return out


@pytest.fixture(autouse=True)
def _reset_sse_exit_event():
    """Cùng lý do như test_api_chat: `sse_starlette` giữ một Event GLOBAL bind vào
    event loop của request SSE đầu tiên, mà TestClient tạo loop mới mỗi request —
    nên request SSE thứ hai nổ 'bound to a different event loop'. Reset về None
    trước mỗi test buộc nó dựng lại trên loop hiện hành."""
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    yield


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client: TestClient) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": "demo-analyst"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _stream(client: TestClient, auth: dict, **body) -> list[tuple[str, dict]]:
    r = client.post("/api/axes/discover/stream", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return _events(r.text)


def test_stream_phat_dung_thu_tu_cong_viec(client: TestClient, auth: dict):
    evs = _stream(client, auth, target="shopcart")
    kinds = [k for k, _ in evs]
    assert kinds[0] == "step", f"sự kiện đầu phải là một bước, thấy {kinds[:3]}"
    assert kinds[-1] == "done"
    names = [p.get("name") for k, p in evs if k == "step"]
    assert "scan_repo" in names
    assert "admit_axes" in names
    assert names.index("scan_repo") < names.index("admit_axes")


def test_stream_phat_tung_truc_mot_su_kien(client: TestClient, auth: dict):
    evs = _stream(client, auth, target="shopcart")
    axes = [p["axis"] for k, p in evs if k == "axis"]
    assert set(axes) == {
        "customer_tier", "shipping_zone", "payment_method", "coupon_type"
    }
    for _k, p in ((k, p) for k, p in evs if k == "axis"):
        assert p["verdict"] in {"locked", "quarantined", "rejected", "floored"}


def test_ket_qua_cuoi_giong_het_ban_rest(client: TestClient, auth: dict):
    """Stream KHÔNG được là một sự thật thứ hai — `done` phải khớp REST."""
    evs = _stream(client, auth, target="shopcart")
    done = next(p for k, p in evs if k == "done")
    rest = client.post("/api/axes/discover", json={"target": "shopcart"}, headers=auth).json()
    assert done["engine"] == rest["engine"]
    assert done["read_only"] == rest["read_only"]
    assert {c["axis"] for c in done["candidates"]} == {c["axis"] for c in rest["candidates"]}
    assert {(c["axis"], c["verdict"]) for c in done["candidates"]} == {
        (c["axis"], c["verdict"]) for c in rest["candidates"]
    }


def test_mock_khai_thang_la_khong_goi_mo_hinh(client: TestClient, auth: dict):
    """Không có mô hình thì nói KHÔNG CÓ, đừng im lặng và đừng giả vờ."""
    assert settings.llm_mode == "mock"
    evs = _stream(client, auth, target="shopcart")
    skipped = [p for k, p in evs if k == "llm_skipped"]
    assert skipped, "mock phải phát llm_skipped"
    assert skipped[0].get("reason"), "phải nói VÌ SAO bỏ, không chỉ một cờ"
    assert not [k for k, _ in evs if k == "llm_delta"], "mock không được phát token"
