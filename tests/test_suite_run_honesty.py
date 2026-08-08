"""Bộ kiểm của repo đích KHÔNG chạy được ⇒ phải nói ra, không được đo tiếp.

Hai lỗi cùng cho ra một triệu chứng — "63/63 ô chưa ai canh" — nhưng nghĩa khác
hẳn nhau, và người đọc không có cách nào phân biệt:

1. `run_target_suite` nuốt exit code khác 0. Bộ kiểm collect fail (thiếu
   dependency, import lỗi) trả về `(exit, set(), (0, 0))` rồi pipeline đi tiếp
   như không có gì. UI hiện "chưa ai canh" — đọc thành *repo này không có test*,
   trong khi sự thật là *CERTUS không chạy được test của repo này*.

2. `code_path` là hằng số `"checkout"` cho MỌI repo. Repo nào không có ký hiệu
   tên `checkout` thì không ô nào chạm tới nó ⇒ `coverage_mismatch` toàn bảng,
   kể cả khi bộ kiểm chạy hoàn hảo.

Cả hai đều biến "tôi không đo được" thành "tôi đã đo và kết quả tệ". Đó đúng là
thứ sản phẩm này tồn tại để chống.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.contracts.errors import CertusError  # noqa: E402
from app.orchestrator.pipeline import (  # noqa: E402
    SuiteRunFailed,
    infer_entry_symbol,
    run_target_suite,
)


# ── lỗi 1: exit code khác 0 phải nổ, không được trả bảng rỗng ────────────────


def test_suite_khong_collect_duoc_thi_no_chu_khong_tra_ve_rong(tmp_path: Path) -> None:
    """Repo có test nhưng import lỗi ⇒ SuiteRunFailed, không phải cov rỗng im lặng."""
    (tmp_path / "app.py").write_text("def handle():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "import khong_ton_tai_dau_ca\n\n\ndef test_x():\n    assert True\n",
        encoding="utf-8",
    )
    with pytest.raises(SuiteRunFailed) as exc:
        run_target_suite(tmp_path)
    # Thông báo phải nói CHUYỆN GÌ XẢY RA, không chỉ một mã số.
    assert "exit" in str(exc.value).lower()
    assert isinstance(exc.value, CertusError)


def test_suite_chay_duoc_thi_tra_ve_binh_thuong(tmp_path: Path) -> None:
    """Đối chứng dương: repo lành thì hàm vẫn trả kết quả, không nổ lung tung."""
    (tmp_path / "app.py").write_text("def handle():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import handle\n\n\ndef test_x():\n    assert handle() == 1\n",
        encoding="utf-8",
    )
    exit_code, cov_suite, (hit, total) = run_target_suite(tmp_path)
    assert exit_code == 0
    assert "app" in cov_suite
    assert total > 0


# ── lỗi 2: code_path phải suy từ repo, không phải hằng số "checkout" ─────────


def test_entry_symbol_suy_tu_repo_chu_khong_phai_hang_so(tmp_path: Path) -> None:
    """Repo không có `checkout` vẫn phải neo được vào một ký hiệu CÓ THẬT."""
    (tmp_path / "ingest.py").write_text(
        "def ingest_document(x):\n    return x\n\n\ndef helper():\n    return 0\n",
        encoding="utf-8",
    )
    cov_suite = {"ingest", "ingest:1", "ingest_document", "helper"}
    symbol = infer_entry_symbol(tmp_path, cov_suite)
    assert symbol in cov_suite, "ký hiệu suy ra phải nằm trong phần đã chạm"
    assert symbol != "checkout"


def test_entry_symbol_uu_tien_ky_hieu_da_duoc_phu(tmp_path: Path) -> None:
    """Giữa hai ứng viên, chọn cái bộ kiểm THẬT SỰ chạm — đó là cái neo được."""
    (tmp_path / "m.py").write_text(
        "def khong_ai_goi():\n    return 0\n\n\ndef duoc_phu():\n    return 1\n",
        encoding="utf-8",
    )
    symbol = infer_entry_symbol(tmp_path, {"m", "duoc_phu"})
    assert symbol == "duoc_phu"


def test_entry_symbol_giu_checkout_cho_repo_mau(tmp_path: Path) -> None:
    """Bất biến: repo mẫu vẫn neo vào `checkout` ⇒ cassette/golden không đổi."""
    (tmp_path / "cart.py").write_text(
        "def checkout(x):\n    return x\n\n\ndef format_money(v):\n    return v\n",
        encoding="utf-8",
    )
    assert infer_entry_symbol(tmp_path, {"cart", "checkout", "format_money"}) == "checkout"


def test_entry_symbol_khong_co_gi_phu_thi_bao_none(tmp_path: Path) -> None:
    """Không suy được thì trả None để nơi gọi khai thẳng, không bịa một cái tên."""
    (tmp_path / "m.py").write_text("def f():\n    return 0\n", encoding="utf-8")
    assert infer_entry_symbol(tmp_path, set()) is None
