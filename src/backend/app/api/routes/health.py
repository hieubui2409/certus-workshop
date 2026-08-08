"""Kiểm tra sức khoẻ — và nói thật về những gì CHƯA sẵn sàng."""

from __future__ import annotations

import shutil
import sys

from fastapi import APIRouter

from app.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Trạng thái sống. Không kiểm gì sâu — đó là việc của /doctor."""
    return {"status": "ok", "llm_mode": settings.llm_mode}


@router.get("/doctor")
def doctor() -> dict:
    """Liệt kê từng thứ và nói rõ thiếu gì.

    Trả về `checks` dạng danh sách chứ không phải một chữ "ok": một endpoint chỉ
    biết trả lời ok/không-ok thì khi nó nói không-ok, người đọc vẫn không biết
    phải đi sửa cái gì.
    """
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # Phiên bản Python là thứ ĐẦU TIÊN phải nói, vì nó là thứ duy nhất ở đây mà
    # người dùng không sửa được bằng một lệnh `pip install`. `scipy==1.15.0` chỉ
    # có wheel tới cp313; trên 3.14 pip quay sang biên dịch từ nguồn và trên
    # Windows sạch nó chết ở "Compiler cl cannot compile programs". Ở buổi chạy
    # thử có người mất cả tối ở đúng chỗ đó rồi bỏ dở — nên nói ra TRƯỚC, chứ
    # không để họ tự tìm ra sau 20 phút tải 59 MB mã nguồn scipy.
    py = sys.version_info
    add(
        "phiên bản Python",
        (3, 11) <= (py.major, py.minor) <= (3, 13),
        f"{py.major}.{py.minor}.{py.micro}"
        + (
            ""
            if (3, 11) <= (py.major, py.minor) <= (3, 13)
            else " — cần 3.11/3.12/3.13. Bản này không có wheel dựng sẵn cho "
            "scipy==1.15.0 nên pip sẽ biên dịch từ nguồn và hỏng trên máy không "
            "có trình biên dịch C. Dựng lại venv bằng 3.12 "
            "(Windows: `py -3.12 -m venv .venv` · macOS/Linux: `python3.12 -m venv .venv`)."
        ),
    )

    for label, path in (
        ("config", settings.config_dir),
        ("repo mẫu", settings.targets_dir),
        ("knowledge base", settings.kb_dir),
        ("cassette", settings.cassette_dir),
    ):
        add(label, path.is_dir(), f"{path} {'có' if path.is_dir() else 'KHÔNG có'}")

    if settings.llm_mode in ("live", "record"):
        # HAI đường vào hợp lệ, không phải một: `anthropic_api_key` (khoá API
        # riêng) HOẶC `anthropic_auth_token` (bearer OAuth, dùng khi thu cassette
        # bằng subscription — xem `Settings.anthropic_auth_token`). Chỉ kiểm cái
        # đầu là doctor báo đỏ trên một hệ thống đang chạy hoàn hảo bằng cái sau,
        # và một chẩn đoán sai như thế đắt hơn không chẩn đoán: người dùng đi
        # sửa cái không hỏng.
        if settings.anthropic_api_key:
            add("API key", True, "có CERTUS_ANTHROPIC_API_KEY")
        elif settings.anthropic_auth_token:
            add("API key", True, "có CERTUS_ANTHROPIC_AUTH_TOKEN (bearer OAuth)")
        else:
            add(
                "API key",
                False,
                f"chế độ {settings.llm_mode} cần CERTUS_ANTHROPIC_API_KEY "
                f"hoặc CERTUS_ANTHROPIC_AUTH_TOKEN",
            )
    else:
        add("API key", True, f"chế độ {settings.llm_mode} không cần key")

    for mod in ("scipy", "statsmodels", "coverage", "anthropic"):
        try:
            __import__(mod)
            add(mod, True, "đã cài")
        except ImportError:
            add(mod, False, f"thiếu — chạy `pip install {mod}`")

    # `import coverage` chạy được KHÔNG có nghĩa là đo được. Bước `run_tests` gọi
    # `coverage` như một CHƯƠNG TRÌNH trong tiến trình con; nếu file thực thi ấy
    # không nằm trên PATH thì suite chết ở exit 126, `.coverage` không sinh ra, và
    # mọi con số phía sau là con số của hư không.
    #
    # Hai thứ này tách nhau trong đời thật: mở terminal mới mà quên activate venv,
    # hoặc trên Windows chạy `python -m certus` bằng interpreter của venv trong khi
    # PATH vẫn là PATH hệ thống — `import` vẫn thấy gói, `PATH` thì không thấy
    # `coverage.exe` trong `Scripts\`. Trước bản này doctor báo 9/9 trong đúng ca
    # đó, và một cái cổng luôn xanh là cái cổng không tồn tại: 32/39 người ở buổi
    # chạy thử nhận 9/9 rồi vẫn ra `grid_coverage 0/63` mà không hiểu vì sao.
    cov_exe = shutil.which("coverage")
    add(
        "coverage chạy được",
        cov_exe is not None,
        f"lệnh `coverage` ở {cov_exe}"
        if cov_exe
        else "KHÔNG thấy lệnh `coverage` trên PATH — bộ kiểm sẽ không chạy được "
        "dù `import coverage` vẫn OK. Activate lại venv "
        "(Windows: .venv\\Scripts\\activate · macOS/Linux: source .venv/bin/activate) "
        "rồi chạy lại lệnh này.",
    )

    failed = [c["name"] for c in checks if not c["ok"]]
    return {
        "ok": not failed,
        "checks": checks,
        "denominator": len(checks),
        "failed": failed,
    }
