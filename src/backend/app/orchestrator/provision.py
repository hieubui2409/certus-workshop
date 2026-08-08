"""Dựng môi trường chạy được cho một repo LẠ, rồi chạy bộ kiểm của nó.

Vì sao cần tệp này: CERTUS đo độ phủ bằng cách CHẠY THẬT bộ kiểm của repo đích.
Nhưng một repo thật hầu như không bao giờ chạy được bằng interpreter của CERTUS
— nó có phiên bản Python riêng, dependency riêng, thường cả một lockfile. Đo
trên một repo không cài được thì `pytest` chết ở bước collect, và mọi con số phủ
phía sau là con số của hư không.

Trước bản này, luồng chỉ chạy đúng một lệnh cố định `coverage run -m pytest -q`
bằng `PATH` của tiến trình cha. Với repo mẫu thì đủ (chúng cố tình không có
dependency), với repo thật thì hỏng ngay từ `import psycopg` trong conftest.

Ba đường dựng, thử theo thứ tự chắc-chắn-giảm-dần:

  1. `uv` + lockfile/pyproject — dựng đúng môi trường repo khai, kể cả khi repo
     đòi Python khác hẳn CERTUS. Đây là đường DUY NHẤT có tái lập thật.
  2. venv sẵn có trong cây (`.venv`) — chỉ dùng khi nó đã có `coverage`, vì thiếu
     là hỏng ở bước đo chứ không phải bước chạy.
  3. interpreter của CERTUS — đường cũ, giữ lại cho repo mẫu và repo không
     dependency. KHÔNG bịa: nếu repo có lockfile mà cả ba đường đều hỏng thì báo
     lỗi nêu đích danh, không âm thầm rơi về đường 3 rồi trả 0% phủ.

Mỗi bước dựng PHÁT RA MỘT DÒNG. Người dùng chờ 2–3 phút cho một bộ kiểm thật, và
2–3 phút im lặng không phân biệt được với treo.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app.contracts.errors import CertusError

__all__ = [
    "ProvisionPlan",
    "SuiteOutcome",
    "detect_plan",
    "default_test_argv",
    "run_suite",
]

#: Lệnh chạy bộ kiểm khi người dùng không khai gì. `coverage run -m pytest -q`
#: là hợp đồng: `.coverage` ở gốc repo là thứ bước `read_coverage` đọc.
#:
#: `-p no:cacheprovider` để không rải `.pytest_cache` vào cây mã người dùng.
#: `--color=no` vì log đi ra UI dưới dạng chữ, mã màu ANSI chỉ thành rác.
#:
#: Giữ `-q` chứ KHÔNG dùng `-v`, dù `-v` cho log mượt hơn nhiều: một bộ kiểm
#: thật có ~1400 test, và mỗi dòng log là một sự kiện SSE. 1400 sự kiện cho một
#: lượt chạy làm ngập cả dòng stream lẫn trình duyệt — đổi một vấn đề hiển thị
#: lấy một vấn đề hiệu năng. `-q` in tiến trình theo dòng ~70 ký tự (một dòng
#: mỗi ~70 test), đủ để thấy nó đang chạy tới đâu mà không dìm UI. Ai cần chi
#: tiết từng test thì khai `-v` ở ô "lệnh chạy bộ kiểm".
DEFAULT_TEST_ARGV = (
    "coverage", "run", "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider",
)


@dataclass(frozen=True)
class ProvisionPlan:
    """Cách chạy bộ kiểm của MỘT repo, kèm lý do chọn cách đó.

    `reason` không phải trang trí: khi con số phủ trông lạ, câu hỏi đầu tiên là
    "đo bằng môi trường nào", và câu trả lời phải có sẵn chứ không phải suy lại.
    """

    argv: tuple[str, ...]
    kind: str  # uv | repo-venv | host
    reason: str
    steps: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class SuiteOutcome:
    """Kết quả một lượt chạy bộ kiểm, tách bạch 'chạy được' khỏi 'test đỏ'."""

    exit_code: int
    plan: ProvisionPlan
    ran: bool  # tiến trình có thực sự chạy tới nơi không (khác với test pass)
    output_tail: str
    #: Vì sao sandbox cắt ngang (hết giờ / ngoài allowlist). None ⇒ chạy tới nơi.
    block_reason: str | None = None


def _has_uv() -> bool:
    return shutil.which("uv") is not None


def _repo_venv_python(root: Path) -> Path | None:
    """Interpreter của venv nằm sẵn trong cây, CHỈ khi nó đã có `coverage`.

    Một venv thiếu `coverage` chạy được pytest nhưng không đo được gì — và
    "chạy được mà không đo được" là ca tệ nhất, vì nó ra 0% trông như một phép
    đo thật. Thà loại nó ở đây để rơi xuống đường kế.
    """
    for name in (".venv", "venv"):
        py = root / name / "bin" / "python"
        if not py.exists():
            continue
        if (root / name / "bin" / "coverage").exists():
            return py
        for site in (root / name / "lib").glob("python*/site-packages/coverage"):
            if site.exists():
                return py
    return None


def detect_plan(root: Path, *, user_argv: list[str] | None = None) -> ProvisionPlan:
    """Chọn cách chạy bộ kiểm cho `root`.

    `user_argv` (người dùng khai) THẮNG mọi suy đoán — đó là điểm của việc cho
    khai. Máy chỉ đoán khi người không nói gì.
    """
    if user_argv:
        return ProvisionPlan(
            argv=tuple(user_argv),
            kind="user",
            reason="lệnh do người dùng khai — không suy đoán gì thêm",
            steps=(f"dùng lệnh người dùng khai: {' '.join(user_argv)}",),
        )

    lock = root / "uv.lock"
    pyproject = root / "pyproject.toml"
    reqs = root / "requirements.txt"

    if _has_uv() and (lock.exists() or pyproject.exists()):
        which = "uv.lock" if lock.exists() else "pyproject.toml"
        return ProvisionPlan(
            # `--with coverage` vì `coverage` gần như không bao giờ nằm trong
            # dependency của repo đích: nó là công cụ ĐO của CERTUS, không phải
            # của repo. Thêm qua `--with` để không phải sửa lockfile người ta.
            argv=("uv", "run", "--with", "coverage", "python", "-m", *DEFAULT_TEST_ARGV),
            kind="uv",
            reason=f"repo khai môi trường ở {which}; uv dựng đúng môi trường đó",
            steps=(
                f"thấy {which} → dựng môi trường bằng uv",
                "thêm `coverage` vào lượt chạy (công cụ đo của CERTUS, không sửa lockfile repo)",
                "uv sẽ tự tải Python + dependency nếu thiếu — lượt đầu có thể lâu",
            ),
        )

    venv_py = _repo_venv_python(root)
    if venv_py is not None:
        return ProvisionPlan(
            argv=(str(venv_py), "-m", *DEFAULT_TEST_ARGV),
            kind="repo-venv",
            reason=f"dùng venv sẵn có trong cây ({venv_py.parent.parent.name}) — đã có coverage",
            steps=(f"thấy venv {venv_py.parent.parent.name}/ có coverage → dùng luôn",),
        )

    if lock.exists() or reqs.exists():
        # Repo KHAI dependency mà ta không có cách dựng. Rơi về host là bịa: nó
        # sẽ chết ở collect rồi trả 0 dòng phủ, trông y hệt "repo không có test".
        raise CertusError(
            f"repo khai dependency ({'uv.lock' if lock.exists() else 'requirements.txt'}) "
            "nhưng máy này không có `uv` và trong cây cũng không có venv nào kèm "
            "`coverage`. Cài uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`), "
            "hoặc tự dựng venv rồi khai lệnh chạy ở ô 'lệnh chạy bộ kiểm'."
        )

    return ProvisionPlan(
        argv=DEFAULT_TEST_ARGV,
        kind="host",
        reason="repo không khai dependency nào — chạy bằng môi trường của CERTUS",
        steps=("repo không có lockfile/venv → chạy bằng môi trường của CERTUS",),
    )


def default_test_argv() -> list[str]:
    return list(DEFAULT_TEST_ARGV)


def run_suite(
    root: Path,
    plan: ProvisionPlan,
    *,
    extra_env: Mapping[str, str] | None = None,
    on_line: Callable[[str], None] | None = None,
    timeout_s: int | None = None,
) -> SuiteOutcome:
    """Chạy bộ kiểm theo `plan`, phát từng dòng log qua `on_line`.

    Vẫn đi qua `run_probe` — allowlist và sổ bằng chứng nằm ở đó, và một lối
    chạy thứ hai dù chỉ để tiện là một lối vòng qua cả hai.
    """
    from app.core.exec.runner import run_probe
    from app.settings import settings

    tail: list[str] = []

    def _sink(line: str) -> None:
        tail.append(line)
        del tail[:-40]  # chỉ giữ đuôi: log đầy đủ đã chảy ra UI rồi
        if on_line is not None:
            on_line(line)

    result = run_probe(
        root,
        list(plan.argv),
        claim_id="target-suite",
        extra_env=extra_env,
        on_line=_sink,
        timeout_s=timeout_s or settings.suite_timeout_seconds,
    )
    return SuiteOutcome(
        exit_code=result.exit_code,
        plan=plan,
        ran=not result.blocked,
        block_reason=result.block_reason,
        output_tail="\n".join(tail),
    )
