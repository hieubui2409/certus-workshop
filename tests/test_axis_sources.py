"""Đề xuất trục đa nguồn — enum + config(Literal) + branch(==/in), tier + dedup."""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.grid.axis_sources import propose_candidates  # noqa: E402


def _write(root: Path, rel: str, code: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code, encoding="utf-8")


def _by_name(cands):
    return {c.name: c for c in cands}


def test_config_literal_becomes_derived_axis(tmp_path):
    _write(tmp_path, "m.py", 'from typing import Literal\ntier: Literal["a", "b", "c"] = "a"\n')
    got = _by_name(propose_candidates(tmp_path, {}, {}))
    assert "tier" in got
    assert got["tier"].origin == "config" and got["tier"].tier == "derived"
    assert got["tier"].members == ("a", "b", "c")
    assert got["tier"].ref.startswith("config:m.py:")


def test_config_literal_in_arg_annotation(tmp_path):
    _write(tmp_path, "m.py", 'from typing import Literal\ndef f(mode: Literal["fast", "slow"]):\n    return mode\n')
    got = _by_name(propose_candidates(tmp_path, {}, {}))
    assert "mode" in got and got["mode"].members == ("fast", "slow")


def test_branch_eq_and_in_become_asserted_axis(tmp_path):
    _write(
        tmp_path, "m.py",
        'def f(fmt, kind):\n'
        '    if fmt == "date":\n        return 1\n'
        '    if fmt == "tax_id":\n        return 2\n'
        '    if kind in ("x", "y", "z"):\n        return 3\n',
    )
    got = _by_name(propose_candidates(tmp_path, {}, {}))
    assert got["fmt"].origin == "branch" and got["fmt"].tier == "asserted"
    assert set(got["fmt"].members) == {"date", "tax_id"}
    assert set(got["kind"].members) == {"x", "y", "z"}


def test_single_literal_branch_is_not_an_axis(tmp_path):
    _write(tmp_path, "m.py", 'def f(state):\n    if state == "only":\n        return 1\n')
    assert "state" not in _by_name(propose_candidates(tmp_path, {}, {}))


def test_enum_wins_over_branch_same_name(tmp_path):
    # `status` xuất hiện cả ở Enum (discovered) lẫn branch → giữ bản Enum (retrieved).
    _write(tmp_path, "m.py", 'def f(status):\n    if status == "a":\n        return 1\n    if status == "b":\n        return 2\n')
    disc = {"status": ["open", "closed"]}
    src = {"status": "e.py::Status"}
    got = _by_name(propose_candidates(tmp_path, disc, src))
    assert got["status"].origin == "enum" and got["status"].tier == "retrieved"
    assert got["status"].members == ("open", "closed")


def test_sources_filter_restricts_origins(tmp_path):
    _write(tmp_path, "m.py", 'from typing import Literal\ny: Literal["a", "b"] = "a"\n')
    got = _by_name(propose_candidates(tmp_path, {}, {}, sources=("enum",)))
    assert "y" not in got  # config bị tắt


def test_private_and_short_names_skipped(tmp_path):
    _write(tmp_path, "m.py", 'def f(x, _secret):\n    if x == "a":\n        return 1\n    if x == "b":\n        return 2\n    if _secret == "p":\n        return 3\n')
    got = _by_name(propose_candidates(tmp_path, {}, {}))
    assert "x" not in got  # tên 1 ký tự bị bỏ
    assert "_secret" not in got  # tên _ bị bỏ


def test_tests_dir_ignored(tmp_path):
    _write(tmp_path, "test_m.py", 'from typing import Literal\nz: Literal["a", "b"] = "a"\n')
    _write(tmp_path, "pkg/tests/helper.py", 'from typing import Literal\nw: Literal["a", "b"] = "a"\n')
    got = _by_name(propose_candidates(tmp_path, {}, {}))
    assert "z" not in got and "w" not in got
