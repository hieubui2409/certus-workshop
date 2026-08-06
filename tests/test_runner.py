"""Ghim hành vi của `core/exec/runner.py`.

Trọng tâm: cấu hình fail-closed, và MỌI lượt chạy đều để lại đúng một record
trong sổ bằng chứng — kể cả lượt bị chặn. Một lượt chạy không có record đọc y
hệt một lượt chưa từng chạy.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.contracts.errors import CertusError, ConfigError  # noqa: E402
from app.core.exec import runner  # noqa: E402
from app.core.exec.runner import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_TIMEOUT,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNVERIFIED,
    ExecConfig,
    exec_config_path,
    load_exec_config,
    run_probe,
)


class FakeLedger:
    """Sổ giả. Chỉ cần khớp Protocol EvidenceLedger."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(
        self,
        *,
        claim_id: str,
        command: str,
        exit_code: int,
        output_sha256: str,
        verdict: str,
    ) -> str:
        self.records.append(
            {
                "claim_id": claim_id,
                "command": command,
                "exit_code": exit_code,
                "output_sha256": output_sha256,
                "verdict": verdict,
            }
        )
        return f"ev-{len(self.records)}"


@pytest.fixture
def cfg() -> ExecConfig:
    return load_exec_config(reload=True)


@pytest.fixture
def ledger() -> FakeLedger:
    return FakeLedger()


# ── cấu hình ────────────────────────────────────────────────────────────


def test_config_that_ships_with_the_repo_loads(cfg: ExecConfig) -> None:
    assert exec_config_path().exists()
    assert "HOME" in cfg.runner.env_passthrough or cfg.runner.env_passthrough
    assert cfg.coverage.min_files_in_report >= 1
    assert 0.0 <= cfg.calibration.false_high_block <= 1.0
    assert cfg.calibration.min_sample_size > 0


def test_every_threshold_lives_in_yaml_not_in_code() -> None:
    """Không field nào của ExecConfig có default.

    Có default nghĩa là thiếu khoá trong yaml vẫn chạy được — và ngưỡng thật
    lúc đó là một con số không ai viết ra ở đâu cả.
    """
    for model in (
        runner.RunnerConfig,
        runner.CoverageConfig,
        runner.MutationConfig,
        runner.CalibrationConfig,
        runner.DockerLimits,
    ):
        for name, info in model.model_fields.items():
            assert info.is_required(), f"{model.__name__}.{name} có default trong code"


def test_missing_key_names_the_key(tmp_path: Path) -> None:
    bad = tmp_path / "exec.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            runner:
              env_passthrough: [PATH]
              max_output_bytes: 1024
              docker:
                mem_limit: "128m"
                pids_limit: 16
                tmpfs_size_bytes: 1024
            coverage:
              min_files_in_report: 1
            mutation:
              timeout_seconds: 10
              max_children: 1
              sample_rate: 0.5
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        load_exec_config(bad, reload=True)
    assert exc.value.key == "calibration"


def test_typo_key_is_an_error_not_a_shrug(tmp_path: Path) -> None:
    good = exec_config_path().read_text(encoding="utf-8")
    bad = tmp_path / "exec.yaml"
    bad.write_text(good.replace("min_sample_size:", "min_sample_sze:"), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_exec_config(bad, reload=True)


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_exec_config(tmp_path / "khong-co.yaml", reload=True)


# ── sổ bằng chứng ───────────────────────────────────────────────────────


def test_ledger_module_without_an_append_surface_refuses_to_run(
    tmp_path: Path, cfg: ExecConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Không có cách ghi sổ ⇒ không chạy. Không có nhánh 'chạy mà không ghi'."""
    empty = ModuleType("app.ledger.evidence")
    # Python gắn module con thành THUỘC TÍNH của gói ở lần import đầu, nên
    # `from app.ledger import evidence` lấy module thật qua getattr và
    # setitem(sys.modules, ...) không còn với tới. Phải vá đúng thuộc tính đó.
    # `from app.ledger import evidence` ưu tiên THUỘC TÍNH của gói hơn
    # sys.modules, nên setitem không với tới. Phải import gói ra trước rồi
    # vá thuộc tính — gói chưa chắc đã được import ở thời điểm test chạy.
    import app.ledger as ledger_pkg
    import app.ledger.evidence  # noqa: F401 — để thuộc tính `evidence` tồn tại

    monkeypatch.setattr(ledger_pkg, "evidence", empty)
    with pytest.raises(CertusError):
        run_probe(tmp_path, ["python", "-c", "pass"], config=cfg)


def test_ledger_is_discovered_through_get_ledger(
    tmp_path: Path, cfg: ExecConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = FakeLedger()
    module = ModuleType("app.ledger.evidence")
    module.get_ledger = lambda: book  # type: ignore[attr-defined]
    # Python gắn module con thành THUỘC TÍNH của gói ở lần import đầu, nên
    # `from app.ledger import evidence` lấy module thật qua getattr và
    # setitem(sys.modules, ...) không còn với tới. Phải vá đúng thuộc tính đó.
    # `from app.ledger import evidence` ưu tiên THUỘC TÍNH của gói hơn
    # sys.modules, nên setitem không với tới. Phải import gói ra trước rồi
    # vá thuộc tính — gói chưa chắc đã được import ở thời điểm test chạy.
    import app.ledger as ledger_pkg
    import app.ledger.evidence  # noqa: F401 — để thuộc tính `evidence` tồn tại

    monkeypatch.setattr(ledger_pkg, "evidence", module)

    result = run_probe(tmp_path, ["python", "-c", "pass"], config=cfg)
    assert result.exit_code == 0
    assert len(book.records) == 1
    assert result.evidence_id == "ev-1"


# ── allowlist ───────────────────────────────────────────────────────────


def test_command_outside_the_allowlist_is_blocked_and_still_logged(
    tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger
) -> None:
    result = run_probe(tmp_path, ["rm", "-rf", "/"], ledger=ledger, config=cfg)

    assert result.blocked is True
    assert result.exit_code == EXIT_BLOCKED
    assert result.block_reason is not None
    assert len(ledger.records) == 1
    assert ledger.records[0]["verdict"] == VERDICT_UNVERIFIED


def test_empty_argv_is_blocked(tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger) -> None:
    result = run_probe(tmp_path, [], ledger=ledger, config=cfg)
    assert result.blocked is True


def test_absolute_path_to_an_allowed_program_is_allowed(
    tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger
) -> None:
    """Gọi bằng đường dẫn tuyệt đối hay bằng tên không được đổi phán quyết."""
    interpreter = Path(sys.executable).with_name("python")
    if not interpreter.exists():
        pytest.skip("bản cài này không có tên 'python'")
    result = run_probe(tmp_path, [str(interpreter), "-c", "pass"], ledger=ledger, config=cfg)
    assert result.blocked is False


# ── thi hành ────────────────────────────────────────────────────────────


def test_exit_code_travels_through_untouched(
    tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger
) -> None:
    """"The exit status is the whole answer" — runner không được diễn giải nó."""
    result = run_probe(
        tmp_path,
        ["python", "-c", "import sys; sys.exit(3)"],
        ledger=ledger,
        config=cfg,
    )
    assert result.exit_code == 3
    assert result.blocked is False
    assert result.passed is False
    assert ledger.records[0]["verdict"] == VERDICT_FAIL


def test_stdout_and_stderr_are_captured_separately(
    tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger
) -> None:
    result = run_probe(
        tmp_path,
        ["python", "-c", "import sys; print('ra'); print('loi', file=sys.stderr)"],
        ledger=ledger,
        config=cfg,
    )
    assert "ra" in result.stdout
    assert "loi" in result.stderr
    assert ledger.records[0]["verdict"] == VERDICT_PASS


def test_output_is_truncated_to_the_configured_ceiling(
    tmp_path: Path, ledger: FakeLedger
) -> None:
    cfg = load_exec_config(reload=True).model_copy(deep=True)
    cfg.runner.max_output_bytes = 64
    result = run_probe(
        tmp_path,
        ["python", "-c", "print('x' * 5000)"],
        ledger=ledger,
        config=cfg,
    )
    assert len(result.stdout.encode()) <= 64


def test_timeout_counts_as_blocked_not_as_a_failing_test(
    tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger
) -> None:
    """Một lượt bị cắt giữa chừng không phải một phép đo."""
    result = run_probe(
        tmp_path,
        ["python", "-c", "import time; time.sleep(30)"],
        ledger=ledger,
        config=cfg,
        timeout_s=1,
    )
    assert result.blocked is True
    assert result.exit_code == EXIT_TIMEOUT
    assert ledger.records[0]["verdict"] == VERDICT_UNVERIFIED


def test_duration_is_measured(tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger) -> None:
    result = run_probe(tmp_path, ["python", "-c", "pass"], ledger=ledger, config=cfg)
    assert result.duration_ms >= 0


def test_child_does_not_leave_pycache_in_the_users_tree(
    tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger
) -> None:
    (tmp_path / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    run_probe(
        tmp_path,
        ["python", "-c", "import helper; print(helper.VALUE)"],
        ledger=ledger,
        config=cfg,
    )
    assert not (tmp_path / "__pycache__").exists()


def test_runs_a_real_pytest_suite(tmp_path: Path, cfg: ExecConfig, ledger: FakeLedger) -> None:
    (tmp_path / "conftest.py").write_text("collect_ignore: list[str] = []\n", encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    result = run_probe(tmp_path, ["pytest", "-q"], ledger=ledger, config=cfg, timeout_s=120)
    assert result.blocked is False
    assert result.exit_code == 0
    assert ledger.records[0]["verdict"] == VERDICT_PASS
