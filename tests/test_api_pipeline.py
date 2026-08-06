"""Tầng nối: orchestrator + API + main.

Tệp này ra đời từ một phép đo, không từ một linh cảm: trước nó, **không một
test nào import `app.orchestrator`, `app.api` hay `app.main`** — 1327 dòng ở
đúng chỗ ghép mọi tầng lại, nằm ngoài mẫu số của 750 test đang xanh.

Đó là hình dạng kinh điển của con số đẹp che một khoảng mù: bộ test không sai,
nó chỉ không nói về phần này. Và phần này là phần duy nhất mà người dùng thật
sự chạm vào.

Test ở đây cố ý **trung lập với trạng thái đúng/sai của sản phẩm**: chúng phải
xanh cả trước lẫn sau khi sinh viên sửa lỗi. Chỗ nào buộc phải chạm tới một lỗi (ví dụ quyền của
`analyst`), test khẳng định phần KHÔNG đổi giữa hai trạng thái.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import AnalyzeRequest, StreamEvent
from app.contracts.errors import CertusError
from app.main import app
from app.orchestrator import observe
from app.orchestrator.pipeline import Pipeline, discover_axes, rate

REPO = Path(__file__).resolve().parents[1]
TARGETS = REPO / "fixtures" / "targets"

#: Đúng 10 loại, khoá bởi SDD 00 §5.
CONTRACT_KINDS = {
    "step", "log", "claim", "cell", "gate", "token", "span", "warning", "done", "error",
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    res = client.post("/api/auth/login", json={"username": "demo-analyst"})
    assert res.status_code == 200, res.text
    return res.json()["token"]


@pytest.fixture(scope="module")
def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── resolve_target: biên tin cậy đầu tiên ────────────────────────────────


@pytest.mark.parametrize(
    "target",
    [
        "..",
        "../..",
        "shopcart/../../..",
        "/etc",
        "/",
        "./../fixtures",
    ],
)
def test_resolve_target_tu_choi_moi_duong_thoat_khoi_thu_muc_repo_mau(target: str) -> None:
    """Không đường dẫn nào được chỉ ra ngoài `fixtures/targets/`.

    Một `..` lọt qua đây nghĩa là người dùng chọn được thư mục bất kỳ trên máy
    để CERTUS chạy `pytest` bên trong — tức là biến chỗ chọn repo thành chỗ
    chạy mã tuỳ ý.
    """
    with pytest.raises(CertusError):
        Pipeline().resolve_target(AnalyzeRequest(target=target))


def test_resolve_target_doi_dung_mot_trong_hai_nguon() -> None:
    """Cả hai hoặc không cái nào đều bị từ chối.

    Nhập nhèm nguồn đầu vào là chỗ đầu tiên biên tin cậy bị xoá nhoà: repo mẫu
    đáng tin và thứ người lạ tải lên không được đi chung một đường.
    """
    with pytest.raises(CertusError):
        Pipeline().resolve_target(AnalyzeRequest())
    with pytest.raises(CertusError):
        Pipeline().resolve_target(AnalyzeRequest(target="shopcart", upload_id="x"))


def test_resolve_target_chap_nhan_repo_mau_that() -> None:
    root = Pipeline().resolve_target(AnalyzeRequest(target="shopcart"))
    assert root.is_dir()
    assert root.name == "shopcart"


# ── rate(): mọi tỉ lệ mang mẫu số ────────────────────────────────────────


def test_rate_tu_choi_mau_so_bang_0() -> None:
    """`n == 0` là ĐỎ, không phải 0%. Không phép tính nào cứu được mẫu số rỗng."""
    with pytest.raises(CertusError):
        rate("thử", 0, 0)


def test_rate_gan_co_khi_mau_so_nho() -> None:
    r = rate("thử", 3, 3)
    assert r.k == 3 and r.n == 3
    assert "n-too-small" in r.flags
    # Điểm ước lượng là 100% nhưng cận dưới thì không.
    assert r.point == 1.0
    assert r.interval.lower < 0.5


def test_rate_khong_gan_co_khi_mau_so_du_lon() -> None:
    r = rate("thử", 90, 100)
    assert "n-too-small" not in r.flags


# ── discover_axes ────────────────────────────────────────────────────────


def test_discover_axes_bo_qua_tep_test() -> None:
    """Enum định nghĩa trong tệp test không được thành trục rủi ro.

    Nếu lọt, mẫu số grid phồng lên theo số bài kiểm — và càng viết thêm test
    thì tỉ lệ phủ càng tệ đi, đúng ngược với điều nó phải đo.
    """
    axes = discover_axes(TARGETS / "shopcart")
    for name, source in axes.source.items():
        assert "test" not in Path(source.split("::")[0]).name, (name, source)


def test_discover_axes_on_dinh_giua_hai_lan_chay() -> None:
    """Cùng repo, hai lần khám phá phải ra cùng trục theo cùng thứ tự.

    Thứ tự trục là axis lock, và axis lock quyết định id của mọi ô. Thứ tự trôi
    nghĩa là hai lượt chạy gọi cùng một ô bằng hai tên, và mọi phép so sánh
    giữa hai lượt mất nghĩa mà không có dấu hiệu nào.
    """
    a = discover_axes(TARGETS / "shopcart")
    b = discover_axes(TARGETS / "shopcart")
    assert list(a.values) == list(b.values)
    assert a.values == b.values


# ── observe ──────────────────────────────────────────────────────────────


def test_lookup_khong_phan_biet_hoa_thuong() -> None:
    table = observe.observations_for_cells(
        [observe.TestFn(name="test_x", file="t.py", line=1,
                        names_used={"vip", "international"}, assert_count=2)],
        code_path="checkout", cov_suite={"checkout"}, suite_exit_code=0,
    )
    assert observe.lookup(table, ("VIP", "INTERNATIONAL")) is not None
    assert observe.lookup(table, ("international", "vip")) is not None
    assert observe.lookup(table, ("vip", "khong-ton-tai")) is None


def test_scan_tests_dem_assert_bang_ast_khong_bang_chu(tmp_path: Path) -> None:
    """`assert` trong chuỗi tài liệu và tên biến không được tính.

    Một mẫu số phồng lên vì đếm nhầm chữ là đúng lớp lỗi mà sản phẩm này tồn
    tại để chống.
    """
    (tmp_path / "test_x.py").write_text(
        '''def test_a():
    """Chuỗi này có chữ assert nhưng không phải một assert."""
    assert_count = 5
    assert assert_count == 5
''',
        encoding="utf-8",
    )
    fns = observe.scan_tests(tmp_path)
    assert len(fns) == 1
    assert fns[0].assert_count == 1


# ── giao thức SSE ────────────────────────────────────────────────────────


def _run_stream(target: str) -> list[StreamEvent]:
    async def go() -> list[StreamEvent]:
        return [ev async for ev in Pipeline().run(AnalyzeRequest(target=target))]

    return asyncio.run(go())


@pytest.fixture(scope="module")
def events() -> list[StreamEvent]:
    return _run_stream("shopcart")


def test_moi_su_kien_nam_trong_hop_dong_10_loai(events: list[StreamEvent]) -> None:
    seen = {ev.kind for ev in events}
    assert seen <= CONTRACT_KINDS, f"phát ra loại ngoài hợp đồng: {seen - CONTRACT_KINDS}"


def test_seq_tang_don_dieu_khong_trung(events: list[StreamEvent]) -> None:
    """Không đánh số thì mất gói trông y hệt xử lý chậm."""
    seqs = [ev.seq for ev in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))


def test_moi_su_kien_mang_cung_mot_trace_id(events: list[StreamEvent]) -> None:
    assert len({ev.trace_id for ev in events}) == 1


def test_stream_ket_thuc_bang_done(events: list[StreamEvent]) -> None:
    assert events[-1].kind == "done"
    assert not any(ev.kind == "error" for ev in events)


def test_wire_data_la_payload_tran_khong_phai_phong_bi(events: list[StreamEvent]) -> None:
    """`data:` phải là payload trần — frontend parse theo hình dạng đó."""
    cell_ev = next(ev for ev in events if ev.kind == "cell")
    data = cell_ev.wire_data()
    assert "payload" not in data
    assert "id" in data["cell"] or "cell" in data


def test_repo_bi_tu_choi_phat_ra_event_error() -> None:
    """Từ chối phải đi ra bằng đúng dòng stream, không nuốt và không nổ."""
    events = _run_stream("khong-ton-tai")
    assert events[-1].kind in ("error", "done")
    assert any(ev.kind == "error" for ev in events)
    err = next(ev for ev in events if ev.kind == "error")
    assert err.payload.get("msg"), "event error phải mang câu chữ đọc được"


# ── HTTP ─────────────────────────────────────────────────────────────────


def test_health_khong_can_token(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_doctor_tra_ve_mau_so(client: TestClient) -> None:
    """`{"ok": false}` nói đúng một bit. Không có mẫu số thì '3 mục hỏng' không
    phân biệt được giữa 3-trên-4 và 3-trên-40."""
    body = client.get("/doctor").json()
    assert body["denominator"] > 0
    assert len(body["checks"]) == body["denominator"]


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/samples"),
        ("post", "/api/analyze"),
        ("get", "/api/config/zones.yaml"),
    ],
)
def test_khong_token_thi_bi_tu_choi(client: TestClient, method: str, path: str) -> None:
    """Thiếu token KHÔNG được rơi về một principal ẩn danh im lặng.

    Đây là test bảo vệ chính cơ chế: `principal_from_header` từng bị cắm vào
    `Depends()` như một hàm thường, khiến FastAPI đọc `authorization` thành
    QUERY PARAM. Khi đó mọi request đều 403 — kiểm quyền *trông như* đang chạy.
    """
    kwargs = {"json": {}} if method == "post" else {}
    res = getattr(client, method)(path, **kwargs)
    assert res.status_code in (401, 403), res.status_code


def test_co_token_thi_di_qua_duoc(client: TestClient, auth: dict[str, str]) -> None:
    """Vế còn lại của test trên: nếu 403 cả khi CÓ token thì cơ chế hỏng theo
    hướng ngược lại, và triệu chứng nhìn giống hệt."""
    res = client.get("/api/samples", headers=auth)
    assert res.status_code == 200, res.text
    assert len(res.json()) >= 3


def test_config_khong_cho_di_ra_ngoai_thu_muc_config(
    client: TestClient, auth: dict[str, str]
) -> None:
    for name in ("../settings.py", "../../../etc/passwd", "settings.py"):
        res = client.get(f"/api/config/{name}", headers=auth)
        assert res.status_code != 200, f"{name} đọc được"


def test_upload_tu_choi_zip_slip(client: TestClient, auth: dict[str, str]) -> None:
    """Một entry tên `../x` ghi ra ngoài thư mục đích."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../thoat.py", "x = 1\n")
        zf.writestr("ok.py", "y = 2\n")
    buf.seek(0)
    res = client.post(
        "/api/upload", headers=auth, files={"file": ("t.zip", buf, "application/zip")}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["files_rejected"] >= 1
    assert any("thoat" in k for k in body["rejected_reasons"])


def test_upload_chi_nhan_zip(client: TestClient, auth: dict[str, str]) -> None:
    res = client.post(
        "/api/upload",
        headers=auth,
        files={"file": ("t.tar", io.BytesIO(b"x"), "application/x-tar")},
    )
    assert res.status_code != 200


def test_coverage_luon_tra_ve_du_ba_tang(client: TestClient, auth: dict[str, str]) -> None:
    """Tầng CHƯA ĐO vẫn phải xuất hiện.

    Bỏ nó đi làm mảng còn hai phần tử, và người đọc kết luận sản phẩm chỉ có
    hai tầng — "chưa đo" biến thành "không tồn tại".
    """
    run = client.post("/api/analyze", headers=auth, json={"target": "shopcart"}).json()
    layers = client.get(f"/api/coverage/{run['run_id']}", headers=auth).json()
    assert isinstance(layers, list)
    assert [x["id"] for x in layers] == ["line", "mutation", "grid"]
    for layer in layers:
        assert layer["denominator_note"], "mỗi tầng phải nói mẫu số của nó là gì"
        if layer["interval"] is None:
            assert "not-measured" in layer["flags"]


def test_khong_co_truong_nao_gop_ba_tang_lai(
    client: TestClient, auth: dict[str, str]
) -> None:
    """Mảng, không phải object: không có chỗ nào để bắt vít một số `overall` vào."""
    run = client.post("/api/analyze", headers=auth, json={"target": "shopcart"}).json()
    layers = client.get(f"/api/coverage/{run['run_id']}", headers=auth).json()
    for layer in layers:
        assert "overall" not in layer
        assert "combined" not in layer


def test_run_id_khong_ton_tai_tra_ve_rong_khong_no(
    client: TestClient, auth: dict[str, str]
) -> None:
    assert client.get("/api/coverage/khong-co-that", headers=auth).json() == []


def test_prompt_payload_liet_ke_ca_hai_danh_sach(
    client: TestClient, auth: dict[str, str]
) -> None:
    """Chỉ hiện danh sách đã gửi thì bộ lọc hỏng và bộ lọc không tồn tại cho ra
    cùng một màn hình."""
    run = client.post("/api/analyze", headers=auth, json={"target": "payments"}).json()
    body = client.get(f"/api/prompt-payload/{run['run_id']}", headers=auth).json()
    assert "files_sent" in body and "files_held" in body
    assert body["blocklist"], "danh sách chặn rỗng đọc y hệt danh sách chặn không tồn tại"
