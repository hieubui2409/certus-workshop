"""Dựng môi trường cho repo lạ + nguồn thứ ba `local_path`.

Vì sao có tệp này: CERTUS đo phủ bằng cách CHẠY THẬT bộ kiểm của repo đích, mà
một repo thật gần như không bao giờ chạy được bằng interpreter của CERTUS. Đo
trên một repo không cài được thì pytest chết ở bước collect, và mọi con số phía
sau là con số của hư không.

Ranh giới mà bộ test này canh:

1. Repo KHAI dependency mà máy không dựng được ⇒ **báo lỗi nêu tên**, KHÔNG âm
   thầm rơi về interpreter của CERTUS rồi trả 0% phủ. "Tôi không đo được" khác
   hẳn "tôi đã đo và kết quả tệ".
2. Người dùng khai lệnh ⇒ máy **không suy đoán gì thêm**.
3. `local_path` là nguồn thứ ba, và ba nguồn phải **loại trừ nhau** — nhập nhèm
   nguồn đầu vào là chỗ đầu tiên một biên tin cậy bị xoá nhoà.
4. Repo thật (kể cả `local_path`) vẫn bị **cổng HITL** chặn như cũ.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.api.schemas import AnalyzeRequest  # noqa: E402
from app.contracts.errors import CertusError  # noqa: E402
from app.orchestrator.pipeline import Pipeline  # noqa: E402
from app.orchestrator.provision import detect_plan  # noqa: E402
from app.settings import settings  # noqa: E402


# ── chọn cách dựng môi trường ──────────────────────────────────────────


def test_lenh_nguoi_dung_khai_thang_moi_suy_doan(tmp_path: Path) -> None:
    """Khai rồi thì máy không được đoán lại — đó là điểm của việc cho khai."""
    (tmp_path / "uv.lock").write_text("")  # có lockfile → máy sẽ chọn uv nếu tự đoán
    plan = detect_plan(tmp_path, user_argv=["pytest", "-q", "-p", "no:randomly"])
    assert plan.kind == "user"
    assert plan.argv == ("pytest", "-q", "-p", "no:randomly")


def test_repo_khong_khai_gi_thi_dung_moi_truong_certus(tmp_path: Path) -> None:
    """Repo mẫu không có lockfile — giữ nguyên đường cũ, không đổi một byte."""
    plan = detect_plan(tmp_path)
    assert plan.kind == "host"
    assert plan.argv[:5] == ("coverage", "run", "-m", "pytest", "-q")


def test_lockfile_ma_khong_dung_duoc_thi_BAO_LOI_chu_khong_am_tham(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ranh giới load-bearing: thà đỏ có lý do còn hơn 0% trông như phép đo.

    Repo khai `uv.lock` mà máy không có `uv` và cây không có venv nào kèm
    `coverage`. Rơi về interpreter của CERTUS ở đây sẽ chết lúc collect rồi trả
    0 dòng phủ — trông y hệt "repo không có test", một kết luận SAI về code
    người dùng rút ra từ một sự cố môi trường.
    """
    monkeypatch.setattr("app.orchestrator.provision._has_uv", lambda: False)
    (tmp_path / "uv.lock").write_text("")
    with pytest.raises(CertusError) as exc:
        detect_plan(tmp_path)
    assert "uv.lock" in str(exc.value)


def test_venv_thieu_coverage_thi_khong_duoc_chon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Venv chạy được pytest nhưng không đo được gì là ca TỆ NHẤT — nó ra 0%
    trông như một phép đo thật. Thà loại để rơi xuống đường sau."""
    monkeypatch.setattr("app.orchestrator.provision._has_uv", lambda: False)
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("")  # có python, KHÔNG coverage
    assert detect_plan(tmp_path).kind == "host"  # không phải repo-venv


def test_venv_co_coverage_thi_duoc_chon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.orchestrator.provision._has_uv", lambda: False)
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("")
    (tmp_path / ".venv" / "bin" / "coverage").write_text("")
    plan = detect_plan(tmp_path)
    assert plan.kind == "repo-venv"
    assert plan.argv[1:7] == ("-m", "coverage", "run", "-m", "pytest", "-q")


def test_uv_them_coverage_vao_luot_chay_khong_sua_lockfile(tmp_path: Path) -> None:
    """`coverage` là công cụ ĐO của CERTUS, không phải dependency của repo —
    thêm qua `--with` để không đụng lockfile người ta."""
    (tmp_path / "uv.lock").write_text("")
    plan = detect_plan(tmp_path)
    if plan.kind != "uv":
        pytest.skip("máy này không có uv")
    assert plan.argv[:5] == ("uv", "run", "--with", "coverage", "python")


# ── nguồn thứ ba: local_path ───────────────────────────────────────────


def _pipe() -> Pipeline:
    return Pipeline(settings)


def test_local_path_tro_thang_thu_muc_co_san(tmp_path: Path) -> None:
    assert _pipe().resolve_target(AnalyzeRequest(local_path=str(tmp_path))) == tmp_path


def test_ba_nguon_loai_tru_nhau(tmp_path: Path) -> None:
    """Nhập nhèm nguồn đầu vào là chỗ đầu tiên một biên tin cậy bị xoá nhoà."""
    for req in (
        AnalyzeRequest(),
        AnalyzeRequest(target="shopcart", local_path=str(tmp_path)),
        AnalyzeRequest(upload_id="abc", local_path=str(tmp_path)),
    ):
        with pytest.raises(CertusError, match="ĐÚNG một"):
            _pipe().resolve_target(req)


def test_local_path_khong_ton_tai_thi_noi_ro(tmp_path: Path) -> None:
    with pytest.raises(CertusError, match="không có thư mục"):
        _pipe().resolve_target(AnalyzeRequest(local_path=str(tmp_path / "khong-co")))


# ── zip bọc một thư mục ────────────────────────────────────────────────


def test_zip_boc_mot_thu_muc_thi_di_xuong(tmp_path: Path) -> None:
    """"Download ZIP" của GitHub bọc repo trong một thư mục mang tên repo.

    Không đi xuống thì mọi thứ dò theo gốc đều trượt: `detect_plan` không thấy
    `uv.lock` nên chọn interpreter của CERTUS, pytest chết ở collect, và lỗi
    hiện ra là "thiếu dependency" chứ không phải "tôi tìm sai chỗ".
    """
    inner = tmp_path / "repo-develop"
    (inner / "src").mkdir(parents=True)
    (inner / "uv.lock").write_text("")
    assert Pipeline._unwrap_single_dir(tmp_path) == inner


def test_zip_trai_phang_thi_o_nguyen(tmp_path: Path) -> None:
    """Có tệp ở cùng tầng ⇒ gốc repo THẬT SỰ ở đây; đi xuống là bỏ qua chính nó."""
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("")
    assert Pipeline._unwrap_single_dir(tmp_path) == tmp_path


def test_hai_thu_muc_thi_khong_doan(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert Pipeline._unwrap_single_dir(tmp_path) == tmp_path


@pytest.mark.anyio
async def test_local_path_van_bi_cong_hitl_chan(tmp_path: Path) -> None:
    """Repo THẬT thì luôn phải chốt trục — `local_path` không phải cửa sau."""
    (tmp_path / "a.py").write_text("x = 1\n")
    events = [ev async for ev in _pipe().run(AnalyzeRequest(local_path=str(tmp_path)))]
    errors = [e for e in events if e.kind == "error"]
    assert errors, "phải phát error, không được lặng lẽ chạy tiếp"
    assert "CHỌN TRỤC" in errors[0].payload["msg"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
