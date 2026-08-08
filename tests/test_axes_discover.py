"""Endpoint khám phá trục — verdict engine cho từng trục (gọi thẳng hàm route)."""

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.api.routes.axes import AxisDiscoveryRequest, axes_discover  # noqa: E402


def _discover(**kw):
    return asyncio.run(axes_discover(AxisDiscoveryRequest(**kw), principal=None))


def test_shopcart_engine_tot_all_locked():
    r = _discover(target="shopcart")
    assert r.engine == "tot"
    assert {c.axis for c in r.candidates} == {
        "customer_tier", "shipping_zone", "payment_method", "coupon_type"
    }
    assert all(c.kept and c.verdict == "locked" for c in r.candidates)
    # ρ hiển thị (leave-one-out) của trục locked phải NHẤT QUÁN verdict: ≥ θ.
    for c in r.candidates:
        assert c.rho is not None and c.rho >= 0.35


def test_ledger_engine_floor_keeps_all():
    r = _discover(target="ledger")
    assert r.engine == "floor"
    assert all(c.kept and c.verdict == "floored" for c in r.candidates)


def test_candidates_carry_source_and_members():
    r = _discover(target="shopcart")
    c = next(c for c in r.candidates if c.axis == "payment_method")
    assert len(c.members) >= 2
    assert "::" in c.source  # neo file::Enum


def test_sample_is_read_only_with_academic_note():
    # Repo mẫu: panel KHÓA (read_only) + note học thuật, tập trục cố định.
    r = _discover(target="shopcart")
    assert r.read_only is True
    assert "Repo mẫu" in (r.note or "")


def test_sample_candidates_are_enum_only():
    # Repo mẫu KHÔNG bật đa nguồn — mọi trục là enum/retrieved (giữ cassette bất biến).
    r = _discover(target="shopcart")
    assert all(c.origin == "enum" and c.tier == "retrieved" for c in r.candidates)


# ── loại trừ thư mục vendor ─────────────────────────────────────────────────


def test_discover_bo_qua_thu_muc_vendor(tmp_path: Path):
    """Enum trong `.venv`/`node_modules` KHÔNG phải trục rủi ro của repo.

    `rglob("*.py")` quét cả cây, nên một repo thật đã `uv sync` sẽ nuốt trọn
    site-packages: `_pytest.ExitCode`, `loguru.TokenType`, `psycopg.ConnStatus`…
    Đo trên document-intake: 97 trục, trong đó 84 đến từ `.venv` — mẫu số nổ
    thành 220k ô và 99% là `unknown`. Đó không phải một phép đo tệ, đó là một
    con số không có nghĩa nào cả, và nó trông y hệt một phép đo.
    """
    from app.orchestrator.pipeline import discover_axes

    (tmp_path / "app.py").write_text(
        "from enum import Enum\n\n\nclass OrderState(Enum):\n"
        "    NEW = 1\n    PAID = 2\n    SHIPPED = 3\n",
        encoding="utf-8",
    )
    vendor = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages" / "_pytest"
    vendor.mkdir(parents=True)
    (vendor / "config.py").write_text(
        "from enum import Enum\n\n\nclass ExitCode(Enum):\n"
        "    OK = 0\n    FAILED = 1\n    INTERNAL = 3\n",
        encoding="utf-8",
    )
    axes = discover_axes(tmp_path)
    assert "order_state" in axes.values, "trục của chính repo phải còn"
    assert "exit_code" not in axes.values, "trục từ .venv phải bị loại"


def test_discover_bo_qua_node_modules_va_build(tmp_path: Path):
    """Cùng luật cho mọi thư mục KHÔNG-phải-mã-nguồn-của-repo."""
    from app.orchestrator.pipeline import discover_axes

    (tmp_path / "core.py").write_text(
        "from enum import Enum\n\n\nclass Tier(Enum):\n    A = 1\n    B = 2\n",
        encoding="utf-8",
    )
    for junk in (".venv", "node_modules", "build", "dist", ".tox", "site-packages"):
        d = tmp_path / junk
        d.mkdir(parents=True, exist_ok=True)
        (d / "x.py").write_text(
            f"from enum import Enum\n\n\nclass Junk{abs(hash(junk)) % 97}(Enum):\n"
            "    P = 1\n    Q = 2\n",
            encoding="utf-8",
        )
    axes = discover_axes(tmp_path)
    assert "tier" in axes.values
    assert len(axes.values) == 1, f"chỉ được 1 trục, thấy: {sorted(axes.values)}"
