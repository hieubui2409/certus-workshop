"""Chạy một lệnh probe trong sandbox và ghi lại bằng chứng.

Đây là chỗ DUY NHẤT trong CERTUS thực sự thi hành mã của người lạ. Mọi module
phía trên chỉ đọc lại artifact mà module này sinh ra, nên mọi thứ ở đây phải
để lại dấu vết: một lượt chạy không có record trong sổ bằng chứng đọc y hệt một
lượt chưa từng chạy, và hai thứ đó cần hai cách xử lý khác nhau.

Giới hạn khai thẳng, không giấu trong docstring dài: chế độ `subprocess` chạy
CÙNG UID với người dùng. Nó là *tamper-evident*, không phải *tamper-proof* —
xem `app/settings.py` và `docs/design/sdd/03-core-exec.md` §8.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.contracts.errors import CertusError, ConfigError, SandboxViolation
from app.settings import settings

# ──────────────────────────────────────────────────────────────────────────
# Cấu hình
# ──────────────────────────────────────────────────────────────────────────


class _Strict(BaseModel):
    """Khoá thừa trong yaml là LỖI, không phải khoá bị lờ đi.

    Một khoá gõ sai mà bị bỏ qua im lặng nghĩa là ngưỡng thật vẫn là default cũ
    trong khi người sửa tin rằng mình đã đổi nó.
    """

    model_config = ConfigDict(extra="forbid")


class DockerLimits(_Strict):
    mem_limit: str
    pids_limit: int
    tmpfs_size_bytes: int


class RunnerConfig(_Strict):
    env_passthrough: list[str]
    max_output_bytes: int
    docker: DockerLimits


class CoverageConfig(_Strict):
    min_files_in_report: int


class MutationConfig(_Strict):
    timeout_seconds: int
    max_children: int
    sample_rate: float


class CalibrationConfig(_Strict):
    revive_fraction: float
    conf: float
    interval_method: str
    min_sample_size: int
    false_high_block: float


class ExecConfig(_Strict):
    """Không field nào có default.

    Luật ba vế: một default trong code là một ngưỡng mất vế "suy ra từ đâu" và
    vế "điều kiện xem lại". Thiếu khoá thì phải dừng và nêu đích danh tên khoá.
    """

    runner: RunnerConfig
    coverage: CoverageConfig
    mutation: MutationConfig
    calibration: CalibrationConfig


_CONFIG_CACHE: dict[Path, ExecConfig] = {}


def exec_config_path() -> Path:
    return settings.config_dir / "exec.yaml"


def load_exec_config(path: Path | None = None, *, reload: bool = False) -> ExecConfig:
    """Đọc `config/exec.yaml`.

    Cache theo đường dẫn vì file này bị đọc ở mỗi lượt chạy probe; `reload=True`
    dành cho test và cho lệnh admin đổi config lúc chạy.
    """
    target = Path(path) if path is not None else exec_config_path()
    if not reload and target in _CONFIG_CACHE:
        return _CONFIG_CACHE[target]

    if not target.exists():
        raise ConfigError("exec.yaml", f"không tìm thấy tệp cấu hình tại {target}")

    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("exec.yaml", "nội dung không phải một mapping")

    try:
        cfg = ExecConfig.model_validate(raw)
    except ValidationError as exc:
        # Nêu ĐÍCH DANH khoá đầu tiên hỏng. "cấu hình không hợp lệ" trơ trọi
        # buộc người sửa phải đi dò, và đi dò là lúc người ta đoán.
        first = exc.errors()[0]
        key = ".".join(str(p) for p in first["loc"])
        raise ConfigError(key, first["msg"]) from exc

    _CONFIG_CACHE[target] = cfg
    return cfg


# ──────────────────────────────────────────────────────────────────────────
# Sổ bằng chứng — Protocol, không tự viết
# ──────────────────────────────────────────────────────────────────────────


class EvidenceLedger(Protocol):
    """Hợp đồng tối thiểu mà runner cần ở sổ bằng chứng.

    Sổ thật thuộc `app/ledger/evidence.py` (SDD 06) — nó lo `prev_hash` và
    `self_hash`. Runner chỉ cần biết cách nộp 5 trường và nhận lại evidence_id.
    Khai Protocol thay vì import cứng để hai module build song song được, và để
    test tiêm được sổ giả mà không đụng vào sổ thật.
    """

    def append(
        self,
        *,
        claim_id: str,
        command: str,
        exit_code: int,
        output_sha256: str,
        verdict: str,
    ) -> str: ...


def _resolve_ledger() -> EvidenceLedger:
    """Tìm sổ thật một lần.

    Không tìm thấy thì RAISE. Cố tình không có nhánh "chạy mà không ghi": nếu
    có, thì mọi lượt chạy trên máy chưa cài ledger sẽ biến mất khỏi lịch sử mà
    không ai thấy — đúng lớp lỗi "xanh câm" mà cả tài liệu nền lẫn sản phẩm này
    tồn tại để chống.
    """
    try:
        from app.ledger import evidence as evidence_module
    except ImportError as exc:  # pragma: no cover - phụ thuộc tiến độ SDD 06
        raise CertusError(
            "không có sổ bằng chứng: app.ledger.evidence chưa tồn tại. "
            "run_probe() từ chối chạy lệnh mà không ghi được record."
        ) from exc

    getter = getattr(evidence_module, "get_ledger", None)
    if callable(getter):
        return getter()
    if hasattr(evidence_module, "append"):
        return evidence_module  # type: ignore[return-value]
    raise CertusError(
        "app.ledger.evidence không cung cấp get_ledger() lẫn append(); "
        "runner không có cách ghi bằng chứng nên từ chối chạy."
    )


# ──────────────────────────────────────────────────────────────────────────
# Kết quả một lượt chạy
# ──────────────────────────────────────────────────────────────────────────

VERDICT_PASS = "executed-pass"
VERDICT_FAIL = "executed-fail"
VERDICT_UNVERIFIED = "UNVERIFIED"

#: Exit code quy ước khi lệnh không bao giờ được thi hành. 126 là quy ước POSIX
#: cho "found but not executable" — gần nghĩa nhất với "bị allowlist từ chối".
EXIT_BLOCKED = 126
#: Quy ước của `timeout(1)`.
EXIT_TIMEOUT = 124


@dataclass(frozen=True)
class ProbeResult:
    """Kết quả một lượt chạy probe.

    `blocked` nghĩa là SANDBOX đã can thiệp, không phải "test hỏng". Phân biệt
    này load-bearing: một lượt bị cắt vì hết giờ không phải một phép đo, và gộp
    nó chung với "test fail" biến một sự cố hạ tầng thành một kết luận về code
    người dùng.
    """

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    blocked: bool = False
    block_reason: str | None = None
    command: str = ""
    evidence_id: str | None = None

    @property
    def passed(self) -> bool:
        return not self.blocked and self.exit_code == 0


# ──────────────────────────────────────────────────────────────────────────
# Allowlist
# ──────────────────────────────────────────────────────────────────────────

#: Chương trình được phép chạy trong sandbox.
#:
#: Danh sách này KHÔNG nằm trong exec.yaml vì nó không phải một ngưỡng: nó không
#: có đơn vị, không có độ nhạy, không có "giá trị khởi điểm minh hoạ". Luật ba
#: vế của SDD 00 §4 nói về ngưỡng.
#: `uv` có mặt vì một repo thật hầu như không bao giờ chạy được bằng interpreter
#: của CERTUS: nó có Python riêng, dependency riêng, thường cả một lockfile. `uv
#: run` là cách dựng đúng môi trường đó mà không bắt người dùng tự cài trước.
ALLOWED_COMMANDS = {"pytest", "coverage", "python", "uv"}


def _is_allowed(argv: list[str]) -> bool:
    """Lệnh có nằm trong allowlist không.

    Lấy `Path(...).name` để `/usr/bin/pytest` và `pytest` cho cùng kết quả —
    người dùng gọi bằng đường dẫn tuyệt đối hay tương đối không đổi phán quyết.
    """
    if not argv:
        return False
    name = Path(argv[0]).name
    if name not in ALLOWED_COMMANDS:
        return False
    # Allowlist theo TÊN chương trình không nói gì về việc chương trình sắp
    # làm gì. `python` được phép, nhưng `python -c` và `python -m` là hai
    # cỗ máy chạy mã tuỳ ý đội lốt một cái tên đã được duyệt.
    if name.startswith("python"):
        rest = argv[1:]
        if any(a in ("-c", "-m") for a in rest):
            allowed_modules = {"pytest", "coverage", "mutmut"}
            try:
                mod = rest[rest.index("-m") + 1]
            except (ValueError, IndexError):
                return False
            return mod in allowed_modules
    return True


# ──────────────────────────────────────────────────────────────────────────
# Thi hành
# ──────────────────────────────────────────────────────────────────────────


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _truncate(text: str, limit: int) -> str:
    if len(text.encode("utf-8", "replace")) <= limit:
        return text
    return text.encode("utf-8", "replace")[:limit].decode("utf-8", "replace")


def _child_env(
    cfg: ExecConfig, run_dir: Path, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Dựng môi trường cho tiến trình con.

    Chỉ những biến khai trong `runner.env_passthrough` được đi xuyên — mặc định
    là allowlist chứ không phải blocklist, vì blocklist luôn thiếu một cái tên.
    Bốn biến còn lại do runner tự đặt và trỏ vào thư mục tạm của lượt chạy, để
    tiến trình con không rải `__pycache__` vào cây mã người dùng và để hai lượt
    chạy cùng đầu vào cho cùng kết quả (PYTHONHASHSEED).

    `extra` là biến NGƯỜI DÙNG khai cho repo đích (vd `VSF_DATABASE_URL`). Nó
    không đi qua allowlist vì allowlist canh biến của MÁY CHỦ rò xuống tiến
    trình con; đây là chiều ngược lại — người dùng chủ động khai cho repo của
    chính họ. Đặt SAU cùng nhưng KHÔNG được đè bốn biến runner tự đặt: chúng là
    thứ giữ cho lượt chạy sạch và tái lập được.
    """
    env = {name: os.environ[name] for name in cfg.runner.env_passthrough if name in os.environ}
    env.setdefault("PATH", os.defpath)
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    env["TMPDIR"] = str(run_dir)
    env["PYTHONPYCACHEPREFIX"] = str(run_dir / "pycache")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    # Không có cái này thì việc đọc-theo-dòng ở trên là vô nghĩa: Python đệm
    # stdout theo KHỐI khi đầu ra không phải terminal, nên pytest chạy 2 phút
    # rưỡi mà log chỉ ra thành 2 lần xả. Người xem thấy im lặng rồi một cục —
    # đúng thứ mà việc stream sinh ra để tránh.
    env["PYTHONUNBUFFERED"] = "1"
    # pytest LUÔN import conftest.py của repo đích, trước mọi test và trước
    # mọi thứ ta kiểm được. Không có cờ nào tắt được điều đó — nên đừng cố
    # ngăn nó chạy; hãy làm cho việc nó chạy không với tới được cái gì.
    #
    # HOME thật đi xuyên qua env_passthrough là chỗ payload ghi được vào
    # thư mục nhà của người dùng. Trỏ HOME vào thư mục chạy tạm.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["HOME"] = str(run_dir)
    return env


def _run_subprocess(
    workspace: Path,
    argv: list[str],
    *,
    cfg: ExecConfig,
    timeout_s: int,
    extra_env: Mapping[str, str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str, str, bool, str | None]:
    """Chạy lệnh; nếu có `on_line` thì đọc output THEO DÒNG và gọi lại ngay.

    `subprocess.run(capture_output=True)` chỉ trả về khi tiến trình đã chết —
    với một bộ kiểm chạy 2–3 phút, đó là 3 phút màn hình trắng. Nhánh `on_line`
    đọc dòng-một để UI thấy tiến trình NGAY khi nó xảy ra. Gộp stderr vào stdout
    ở nhánh này có chủ đích: người đọc log cần thấy đúng thứ tự thời gian giữa
    hai luồng, mà hai ống riêng thì không có cách nào ghép lại đúng thứ tự.
    """
    run_dir = Path(tempfile.mkdtemp(prefix="certus-probe-"))
    env = _child_env(cfg, run_dir, extra_env)
    try:
        if on_line is None:
            proc = subprocess.run(  # noqa: S603 - argv đã qua _is_allowed
                argv,
                cwd=str(workspace),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            return proc.returncode, proc.stdout, proc.stderr, False, None

        lines: list[str] = []
        deadline = time.monotonic() + timeout_s
        popen = subprocess.Popen(  # noqa: S603 - argv đã qua _is_allowed
            argv,
            cwd=str(workspace),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            assert popen.stdout is not None
            for raw in popen.stdout:
                line = raw.rstrip("\n")
                lines.append(line)
                on_line(line)
                if time.monotonic() > deadline:
                    popen.kill()
                    return (
                        EXIT_TIMEOUT, "\n".join(lines), "", True,
                        f"quá thời gian {timeout_s}s",
                    )
            code = popen.wait(timeout=max(1, int(deadline - time.monotonic())))
        finally:
            if popen.poll() is None:
                popen.kill()
        return code, "\n".join(lines), "", False, None
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return EXIT_TIMEOUT, out, err, True, f"quá thời gian {timeout_s}s"
    except FileNotFoundError as exc:
        return EXIT_BLOCKED, "", str(exc), True, "không tìm thấy chương trình"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def _run_docker(
    workspace: Path, argv: list[str], *, cfg: ExecConfig, timeout_s: int
) -> tuple[int, str, str, bool, str | None]:
    """Chạy trong container: mount read-only, không mạng, có trần tài nguyên.

    Dùng docker SDK chứ không gọi CLI `docker run`: SDK trả exit code và log ở
    dạng có cấu trúc, còn parse stdout của CLI là đúng thứ luật nhà cấm.
    """
    try:
        import docker  # type: ignore[import-not-found]
        from docker.errors import DockerException  # type: ignore[import-not-found]
    except ImportError as exc:
        raise CertusError(
            "sandbox_mode='docker' nhưng chưa cài docker SDK. Đổi "
            "CERTUS_SANDBOX_MODE=subprocess hoặc cài `docker`."
        ) from exc

    limits = cfg.runner.docker
    container = None
    try:
        client = docker.from_env()
        container = client.containers.run(
            image=settings.sandbox_image,
            command=argv,
            working_dir="/workspace",
            volumes={str(workspace.resolve()): {"bind": "/workspace", "mode": "ro"}},
            environment=_child_env(cfg, Path("/tmp")),
            network_disabled=True,
            read_only=True,
            mem_limit=limits.mem_limit,
            pids_limit=limits.pids_limit,
            # Mount read-only nên mọi thứ ghi ra đều phải rơi vào tmpfs này.
            tmpfs={"/tmp": f"rw,size={limits.tmpfs_size_bytes}"},
            user=f"{os.getuid()}:{os.getgid()}",
            detach=True,
        )
        status = container.wait(timeout=timeout_s)
        exit_code = int(status.get("StatusCode", EXIT_BLOCKED))
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", "replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", "replace")
        return exit_code, stdout, stderr, False, None
    except DockerException as exc:
        # Sandbox không dựng được KHÔNG phải "test fail" — nó là UNVERIFIED.
        return EXIT_BLOCKED, "", str(exc), True, f"sandbox docker lỗi: {exc}"
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception as exc:  # noqa: BLE001 - dọn rác không được che lỗi chính
                import logging

                logging.getLogger(__name__).warning("không xoá được container: %s", exc)


def run_probe(
    workspace: Path,
    argv: list[str],
    *,
    ledger: EvidenceLedger | None = None,
    claim_id: str = "probe",
    timeout_s: int | None = None,
    config: ExecConfig | None = None,
    extra_env: Mapping[str, str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> ProbeResult:
    """Chạy `argv` trong `workspace` và ghi đúng một record vào sổ bằng chứng.

    Ghi sổ nằm ở nhánh chung — lệnh bị chặn cũng có record, với verdict
    UNVERIFIED. "Không có gì để soi" phải NHÌN THẤY được trong sổ, chứ không
    được biểu hiện bằng sự vắng mặt của một dòng.

    `extra_env`: biến môi trường người dùng khai cho repo đích. `on_line`: gọi
    lại cho TỪNG dòng output ngay khi nó ra — chỉ đường subprocess; docker vẫn
    gom log ở cuối vì SDK trả log theo lô.
    """
    cfg = config or load_exec_config()
    book = ledger if ledger is not None else _resolve_ledger()
    limit = timeout_s if timeout_s is not None else settings.probe_timeout_seconds
    command = shlex.join(argv)

    started = time.perf_counter()
    if not _is_allowed(argv):
        reason = f"lệnh không nằm trong allowlist {sorted(ALLOWED_COMMANDS)}"
        exit_code, stdout, stderr, blocked, block_reason = (
            EXIT_BLOCKED,
            "",
            SandboxViolation(argv, reason).args[0],
            True,
            reason,
        )
    elif settings.sandbox_mode == "docker":
        exit_code, stdout, stderr, blocked, block_reason = _run_docker(
            workspace, argv, cfg=cfg, timeout_s=limit
        )
    else:
        exit_code, stdout, stderr, blocked, block_reason = _run_subprocess(
            workspace, argv, cfg=cfg, timeout_s=limit,
            extra_env=extra_env, on_line=on_line,
        )
    duration_ms = int((time.perf_counter() - started) * 1000)

    stdout = _truncate(stdout, cfg.runner.max_output_bytes)
    stderr = _truncate(stderr, cfg.runner.max_output_bytes)

    if blocked:
        verdict = VERDICT_UNVERIFIED
    elif exit_code == 0:
        verdict = VERDICT_PASS
    else:
        verdict = VERDICT_FAIL

    evidence_id = book.append(
        claim_id=claim_id,
        command=command,
        exit_code=exit_code,
        output_sha256=_sha256(stdout + stderr),
        verdict=verdict,
    )

    return ProbeResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        blocked=blocked,
        block_reason=block_reason,
        command=command,
        evidence_id=evidence_id,
    )


__all__ = [
    "ALLOWED_COMMANDS",
    "CalibrationConfig",
    "CoverageConfig",
    "EvidenceLedger",
    "ExecConfig",
    "MutationConfig",
    "ProbeResult",
    "RunnerConfig",
    "exec_config_path",
    "load_exec_config",
    "run_probe",
]
