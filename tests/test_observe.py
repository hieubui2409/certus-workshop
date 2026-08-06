"""Loader + injector mutation replay: artifact precomputed → mutation_run của ô.

Neo hai luật: (1) thiếu bằng chứng là fail-closed, không phải "coi như đã kiểm";
(2) verdict chỉ phủ đúng zone artifact khai, không mượn sang zone khác.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.orchestrator.observe import (  # noqa: E402
    load_mutation_artifact,
    mutation_run_for_cell,
)

_VALID = {
    "target": "shopcart",
    "zone_id": "payment_critical",
    "verdict": "killed",
    "seed_id": "mut-shopcart-abc123",
    "probe_sha256": "deadbeef",
    "operator": "if x: → if not x:",
    "target_path": "shopcart/payment.py",
}


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_load_returns_none_when_absent(tmp_path: Path) -> None:
    """Không có file ⇒ None ⇒ cổng mutation giữ fail-closed."""
    assert load_mutation_artifact("shopcart", tmp_path) is None


def test_load_valid_artifact(tmp_path: Path) -> None:
    _write(tmp_path, "shopcart.json", _VALID)
    art = load_mutation_artifact("shopcart", tmp_path)
    assert art is not None and art["verdict"] == "killed"


@pytest.mark.parametrize("missing", sorted(_VALID))
def test_load_rejects_artifact_missing_any_required_key(
    tmp_path: Path, missing: str
) -> None:
    """Thiếu MỘT khoá bắt buộc ⇒ bỏ qua, không nâng band bằng artifact khuyết."""
    data = {k: v for k, v in _VALID.items() if k != missing}
    _write(tmp_path, "shopcart.json", data)
    assert load_mutation_artifact("shopcart", tmp_path) is None


def test_load_rejects_target_mismatch(tmp_path: Path) -> None:
    _write(tmp_path, "shopcart.json", {**_VALID, "target": "payments"})
    assert load_mutation_artifact("shopcart", tmp_path) is None


def test_load_rejects_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / "shopcart.json").write_text("{ not json", encoding="utf-8")
    assert load_mutation_artifact("shopcart", tmp_path) is None


def test_run_for_cell_binds_five_fields_in_matching_zone() -> None:
    run = mutation_run_for_cell(_VALID, zone_id="payment_critical", cell_id="c-1")
    assert run is not None
    assert run["verdict"] == "killed"
    assert run["seed_id"] == _VALID["seed_id"]
    assert run["round_had_survived"] is False
    binding = run["binding"]
    # Đủ 5 trường mà grid.yaml mutation_binding_fields đòi, mọi trường truthy.
    for field in ("probe_sha256", "seed_id", "cell_id", "operator", "target_path"):
        assert binding.get(field), f"binding thiếu {field}"
    assert binding["cell_id"] == "c-1"


def test_run_for_cell_none_outside_declared_zone() -> None:
    """Zone khác ⇒ None ⇒ không mượn verdict sang zone chưa chạy mutmut."""
    assert mutation_run_for_cell(_VALID, zone_id="concurrency", cell_id="c-1") is None
    assert mutation_run_for_cell(_VALID, zone_id="checkout_core", cell_id="c-1") is None


def test_run_for_cell_none_when_no_artifact() -> None:
    assert mutation_run_for_cell(None, zone_id="payment_critical", cell_id="c-1") is None
