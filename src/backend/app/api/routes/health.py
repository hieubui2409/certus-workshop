"""Kiểm tra sức khoẻ — và nói thật về những gì CHƯA sẵn sàng."""

from __future__ import annotations

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

    for label, path in (
        ("config", settings.config_dir),
        ("repo mẫu", settings.targets_dir),
        ("knowledge base", settings.kb_dir),
        ("cassette", settings.cassette_dir),
    ):
        add(label, path.is_dir(), f"{path} {'có' if path.is_dir() else 'KHÔNG có'}")

    if settings.llm_mode == "live":
        add(
            "API key",
            bool(settings.anthropic_api_key),
            "chế độ live cần CERTUS_ANTHROPIC_API_KEY",
        )
    else:
        add("API key", True, f"chế độ {settings.llm_mode} không cần key")

    for mod in ("scipy", "statsmodels", "coverage", "anthropic"):
        try:
            __import__(mod)
            add(mod, True, "đã cài")
        except ImportError:
            add(mod, False, f"thiếu — chạy `pip install {mod}`")

    failed = [c["name"] for c in checks if not c["ok"]]
    return {
        "ok": not failed,
        "checks": checks,
        "denominator": len(checks),
        "failed": failed,
    }
