"""Không scope nào được khai mà không có nơi cưỡng chế.

Tệp này ra đời từ một lỗ hổng ĐO ĐƯỢC, không từ một nguyên tắc chung: bảng
`ROLE_SCOPES` khai 9 quyền, nhưng chỉ `config:read` và `config:write` từng được
`require()` gọi tới. Bảy quyền còn lại là chữ trong một dict.

Hậu quả đo được lúc đó:

    POST /api/analyze  bằng token `demo-viewer` (scopes: gate:read, grid:read,
    repo:read — KHÔNG có probe:run)  →  **200 OK**

Tức là vai chỉ-đọc chạy được `pytest` bên trong repo đích. Bảng phân quyền đọc
như đang bảo vệ, và chính vì thế không ai đi kiểm nó.

Đây là cùng một hình dạng với luật của chính sản phẩm: *một cổng chỉ là cổng
nếu nó đã từng hạ xuống.* Một scope chỉ là quyền nếu đã từng có ai bị nó chặn.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.scopes import ROLE_SCOPES
from app.main import app

BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
API = BACKEND / "app" / "api"

#: Scope không gắn với endpoint nào — phải khai ở đây KÈM LÝ DO.
#:
#: Danh sách này cố ý gây khó chịu: thêm một dòng vào đây là một hành động có
#: chủ ý, người viết phải gõ ra lý do. Không có nó, cách "sửa" test này rẻ nhất
#: sẽ là im lặng bỏ qua mọi scope chưa dùng — và ta quay lại đúng chỗ cũ.
INTERNAL_ONLY: dict[str, str] = {
    "gate:override": (
        "Chưa có endpoint override. Giữ trong bảng vì nó là quyền có thật trong "
        "thiết kế cổng chặn; ngày nào có endpoint, nó phải được require() ngay."
    ),
    "grid:project": (
        "Việc chiếu band chạy trong tiến trình phân tích, không lộ ra HTTP. "
        "Người dùng không tự gọi được nên không có chỗ để kiểm."
    ),
    "ledger:append": (
        "Ghi sổ là hệ quả của một thao tác khác (chạy probe, đổi cấu hình), "
        "không phải một endpoint riêng. Quyền ghi sổ đi kèm quyền gây ra nó."
    ),
}


def _enforced_scopes() -> set[str]:
    """Scope thật sự xuất hiện trong một lời gọi cưỡng chế ở tầng API.

    Quét mã nguồn chứ không quét bảng: bảng là thứ đang bị nghi ngờ.
    """
    found: set[str] = set()
    pattern = re.compile(r"""(?:needs|require)\(\s*["']([a-z]+:[a-z]+)["']""")
    for path in API.rglob("*.py"):
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def test_moi_scope_deu_co_noi_cuong_che_hoac_ly_do() -> None:
    declared = {s for scopes in ROLE_SCOPES.values() for s in scopes}
    enforced = _enforced_scopes()

    # Mẫu số phải khác 0. Một regex hỏng sẽ trả về tập rỗng, và khi đó phép
    # kiểm bên dưới vẫn "chạy" nhưng không kiểm gì.
    assert enforced, "không tìm thấy lời gọi cưỡng chế nào — bộ quét đang hỏng"

    orphans = declared - enforced - set(INTERNAL_ONLY)
    assert not orphans, (
        f"{len(orphans)} scope được khai nhưng không nơi nào cưỡng chế: "
        f"{sorted(orphans)}. Mỗi cái là một quyền mà người đọc bảng tưởng đang "
        f"có hiệu lực. Hoặc gắn nó vào một route, hoặc khai vào INTERNAL_ONLY "
        f"kèm lý do."
    )


def test_khong_khai_thua_trong_internal_only() -> None:
    """Lý do miễn trừ phải còn đúng.

    Một dòng miễn trừ cho scope đã được cưỡng chế ở đâu đó là rác — và rác
    trong danh sách miễn trừ chính là cách danh sách miễn trừ phình ra cho tới
    khi nó che hết mọi thứ.
    """
    enforced = _enforced_scopes()
    thua = set(INTERNAL_ONLY) & enforced
    assert not thua, f"đã cưỡng chế rồi nhưng vẫn khai miễn trừ: {sorted(thua)}"

    declared = {s for scopes in ROLE_SCOPES.values() for s in scopes}
    khong_ton_tai = set(INTERNAL_ONLY) - declared
    assert not khong_ton_tai, (
        f"miễn trừ cho scope không có trong bảng: {sorted(khong_ton_tai)}"
    )


def test_moi_ly_do_mien_tru_la_cau_chu_that() -> None:
    for scope, reason in INTERNAL_ONLY.items():
        assert len(reason) > 40, f"{scope}: lý do quá ngắn để nói được điều gì"


# ── đối chứng hành vi: quyền phải THẬT SỰ chặn ───────────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _token(client: TestClient, username: str) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": username})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def test_viewer_khong_chay_duoc_probe(client: TestClient) -> None:
    """Đây là ca đã từng trả 200. Nó phải trả 403.

    Không có test này, bản vá scope chỉ là một dòng code chưa ai chứng minh là
    có tác dụng.
    """
    res = client.post(
        "/api/analyze", headers=_token(client, "demo-viewer"), json={"target": "shopcart"}
    )
    assert res.status_code == 403, f"viewer chạy được probe: {res.status_code}"


def test_viewer_khong_doc_duoc_cau_hinh(client: TestClient) -> None:
    res = client.get("/api/config/zones.yaml", headers=_token(client, "demo-viewer"))
    assert res.status_code == 403


def test_viewer_van_doc_duoc_thu_thuoc_quyen_minh(client: TestClient) -> None:
    """Vế còn lại: nếu chặn cả thứ viewer ĐƯỢC phép, ta chỉ đổi một lỗi lấy một
    lỗi khác — và lỗi mới khó thấy hơn vì nó trông như đang an toàn."""
    res = client.get("/api/samples", headers=_token(client, "demo-viewer"))
    assert res.status_code == 200, res.text


def test_analyst_chay_duoc_probe(client: TestClient) -> None:
    res = client.post(
        "/api/analyze", headers=_token(client, "demo-analyst"), json={"target": "shopcart"}
    )
    assert res.status_code == 200, res.text
