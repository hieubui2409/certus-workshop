"""Vá lỗ zip-bomb ở /api/upload: trần từng tệp và trần tổng đo qua HTTP thật.

Lỗ cố ý đo được (upload.py:53,58 trước bản vá): `policy.decide(name)` gọi
KHÔNG truyền `size_bytes`, nên `max_file_bytes` (256 KiB, config/data-policy.
yaml) không bao giờ chạy — một entry khai kích thước lớn vẫn được `zf.read()`
giải nén trọn vào RAM. Test dưới đây đo đúng hai lớp phòng thủ đã thêm: (1)
trần từng tệp qua `policy.decide(name, size_bytes=...)`, (2) trần TỔNG cho cả
lượt upload (`settings.upload_max_total_bytes`) chặn ca nhiều tệp nhỏ cộng dồn.
Lớp thứ ba (`_read_bounded` không tin `zinfo.file_size`) được test trực tiếp,
không qua HTTP, vì zipfile không có API bình thường để khai một header nói dối.
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.api.routes.upload import _read_bounded  # noqa: E402
from app.api.schemas import AcceptedFile, UploadAck  # noqa: E402
from app.contracts.errors import CertusError  # noqa: E402
from app.main import app  # noqa: E402
from app.policy.data_policy import load_policy  # noqa: E402
from app.settings import settings  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client: TestClient) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": "demo-viewer"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _zip_with_one_file(name: str, data: bytes) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, data)
    buf.seek(0)
    return buf


# ------------------------------------------------------- lớp 1: trần từng tệp


def test_tep_vuot_max_file_bytes_bi_tu_choi_khong_duoc_nhan(
    client: TestClient, auth: dict[str, str]
) -> None:
    """Trước bản vá: `policy.decide(name)` không truyền `size_bytes` nên một
    tệp vượt hẳn `max_file_bytes` (256 KiB) vẫn được nhận. Đo lại: phải bị từ
    chối, và lý do phải nêu đích danh ngưỡng `max_file_bytes`."""
    policy = load_policy()
    oversized = b"a" * (policy.max_file_bytes + 1024)
    buf = _zip_with_one_file("qua_kho.py", oversized)
    res = client.post(
        "/api/upload", headers=auth, files={"file": ("t.zip", buf, "application/zip")}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["files_accepted"] == 0
    assert body["files_rejected"] == 1
    reason = body["rejected_reasons"]["qua_kho.py"]
    assert "max_file_bytes" in reason, reason


def test_tep_duoi_max_file_bytes_van_duoc_nhan_binh_thuong(
    client: TestClient, auth: dict[str, str]
) -> None:
    """Vế đối chứng: bản vá không được biến tệp hợp lệ thành bị chặn nhầm."""
    policy = load_policy()
    small = b"x = 1\n" * 10
    assert len(small) < policy.max_file_bytes
    buf = _zip_with_one_file("nho.py", small)
    res = client.post(
        "/api/upload", headers=auth, files={"file": ("t.zip", buf, "application/zip")}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["files_accepted"] == 1
    assert body["files_rejected"] == 0
    assert body["bytes_total"] == len(small)


# --------------------------------------------------------- lớp 2: trần tổng


def test_nhieu_tep_duoi_tran_rieng_cong_don_vuot_tran_tong_bi_tu_choi(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mỗi tệp riêng lẻ dưới `max_file_bytes` nhưng cộng dồn vượt trần TỔNG của
    cả lượt upload — đây chính là ca `max_file_bytes` không chặn được vì nó chỉ
    nhìn từng tệp một, không nhìn tổng."""
    policy = load_policy()
    per_file = policy.max_file_bytes // 2
    # Trần tổng chỉ đủ cho đúng 3 tệp — tệp thứ 4 phải bị từ chối.
    monkeypatch.setattr(settings, "upload_max_total_bytes", per_file * 3)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(4):
            zf.writestr(f"phan_{i}.py", b"a" * per_file)
    buf.seek(0)

    res = client.post(
        "/api/upload", headers=auth, files={"file": ("t.zip", buf, "application/zip")}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["files_accepted"] == 3, body
    assert body["files_rejected"] == 1, body
    reason = next(iter(body["rejected_reasons"].values()))
    assert "tổng" in reason or "trần" in reason, reason
    assert body["bytes_total"] <= per_file * 3


# ------------------------------------------- lớp 3: không tin header khai báo


def test_read_bounded_huy_khi_byte_that_vuot_tran_du_khong_ai_khai_bao_truoc(
    tmp_path: Path,
) -> None:
    """`_read_bounded` phải huỷ dựa trên byte THẬT đang chảy ra, không dựa vào
    bất kỳ con số nào được khai trước — mô phỏng đúng ca header nói dối mà lớp
    1 (kiểm `zinfo.file_size` trước khi đọc) không tự chặn được."""
    raw = tmp_path / "t.zip"
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("to.bin", b"a" * 100_000)

    with zipfile.ZipFile(raw) as zf:
        # Giới hạn cố tình nhỏ hơn hẳn dữ liệu thật — không liên quan gì tới
        # zinfo.file_size (100_000) mà "_read_bounded" cũng không được đọc.
        with pytest.raises(CertusError):
            _read_bounded(zf, "to.bin", limit=1024)


def test_read_bounded_cho_qua_khi_byte_that_nam_trong_tran(tmp_path: Path) -> None:
    raw = tmp_path / "t.zip"
    data = b"a" * 2048
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("vua.bin", data)

    with zipfile.ZipFile(raw) as zf:
        out = _read_bounded(zf, "vua.bin", limit=4096)
    assert out == data


# --------------------------------------------------- biên lai: số phải có neo


def test_ack_liet_ke_tung_tep_da_nhan_kem_bam_noi_dung_that(
    client: TestClient, auth: dict[str, str]
) -> None:
    """`files_accepted` phải đi kèm DANH SÁCH, không đứng một mình.

    Trước bản vá `/api/upload` chỉ trả một con số đếm, còn UI dựng bảng từ
    danh sách — nên màn hình in "Đã nhận 0 tệp" ngay dưới một lượt nạp 14 tệp
    thành công. Một con số không neo vào thứ nó đếm thì không ai kiểm được nó,
    kể cả khi nó đúng: đúng luật CERTUS dạy người khác.
    """
    a = b"x = 1\n"
    b = b"y = 2\n" * 3
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pkg/a.py", a)
        zf.writestr("pkg/b.py", b)
    buf.seek(0)

    res = client.post(
        "/api/upload", headers=auth, files={"file": ("t.zip", buf, "application/zip")}
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["files_accepted"] == len(body["accepted"]) == 2, body
    got = {f["path"]: f for f in body["accepted"]}
    assert set(got) == {"pkg/a.py", "pkg/b.py"}
    # Băm phải là băm của BYTE THẬT đã ghi ra đĩa, không phải của gì khai
    # trong header zip.
    assert got["pkg/a.py"]["sha256"] == hashlib.sha256(a).hexdigest()
    assert got["pkg/b.py"]["bytes"] == len(b)
    assert body["bytes_total"] == len(a) + len(b)


def test_ack_tu_choi_khi_so_dem_lech_khoi_danh_sach() -> None:
    """Bất biến được cưỡng chế tại schema, không chỉ trong tài liệu."""
    with pytest.raises(ValidationError):
        UploadAck(
            upload_id="deadbeef",
            accepted=[AcceptedFile(path="a.py", bytes=1, sha256="00")],
            files_accepted=14,
            files_rejected=0,
            bytes_total=1,
        )
