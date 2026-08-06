"""Chính sách dữ liệu: tệp nào của người dùng được rời khỏi máy này.

Đây là biên tin cậy trong `system-design.md` §3.1. Mọi thứ đi qua đây phải được
coi là DỮ LIỆU, không phải LỆNH — và một phần trong đó không được đi qua chút nào.

Quyết định là `PolicyDecision`, luôn kèm `reason` bằng tiếng Việt hiển thị được
thẳng lên UI: một tệp biến mất khỏi payload mà không có lý do đọc được thì
người dùng không phân biệt được "bị chặn" với "quên mất".

Fail-closed: `config/data-policy.yaml` thiếu khoá ⇒ `ConfigError` nêu đích danh
tên khoá, không rơi về giá trị mặc định trong code.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import BaseModel

from app.contracts.errors import ConfigError
from app.policy.redaction import build_blocklist, redact_text
from app.settings import settings

#: Khoá bắt buộc phải có mặt trong tệp cấu hình. Thiếu một khoá là lỗi cấu
#: hình, không phải một lượt chạy "lỏng hơn một chút".
REQUIRED_KEYS = ("max_file_bytes", "binary_extensions", "blocklist_extra", "redact_placeholder")

CONFIG_FILENAME = "data-policy.yaml"


class PolicyDecision(BaseModel):
    """Phán quyết cho đúng một tệp. `matched_pattern` để người dùng sửa được
    chính sách thay vì chỉ biết mình bị chặn."""

    path: str
    allowed: bool
    reason: str
    matched_pattern: str | None = None


class DataPolicy:
    """Luật lọc đã nạp. Đối tượng bất biến sau khi `load()`."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self.blocklist: list[str] = build_blocklist(cfg)
        self.max_file_bytes: int = int(cfg["max_file_bytes"])
        self.binary_extensions: set[str] = {
            e.lower() if e.startswith(".") else f".{e.lower()}" for e in cfg["binary_extensions"]
        }
        self.redact_placeholder: str = str(cfg["redact_placeholder"])
        self.allowlist_exact: dict[str, str] = _parse_allowlist(cfg.get("allowlist_exact") or [])

    # ------------------------------------------------------------------ nạp

    @classmethod
    def load(cls, path: Path | str | None = None) -> DataPolicy:
        cfg_path = Path(path) if path is not None else Path(settings.config_dir) / CONFIG_FILENAME
        if not cfg_path.exists():
            raise ConfigError(str(cfg_path), "tệp cấu hình data policy không tồn tại")
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigError(str(cfg_path), "nội dung không phải một mapping YAML")
        for key in REQUIRED_KEYS:
            if key not in raw:
                raise ConfigError(key, f"thiếu trong {cfg_path}")
        return cls(raw)

    # ------------------------------------------------------------- phán xử

    def decide(self, rel_path: str, size_bytes: int | None = None) -> PolicyDecision:
        """First-match-wins, và thứ tự dưới đây là load-bearing.

        Allowlist đứng TRƯỚC blocklist vì nó tồn tại đúng để giải những ca mà
        blocklist chặn nhầm (`.env.example`), và nó khớp theo tên nguyên văn
        nên phạm vi của nó hẹp bằng đúng một tệp.
        """
        name = Path(rel_path).name

        if name in self.allowlist_exact:
            return PolicyDecision(
                path=rel_path,
                allowed=True,
                reason=f"nằm trong allowlist: {self.allowlist_exact[name]}",
                matched_pattern=name,
            )

        for pattern in self.blocklist:
            if fnmatch(name, pattern) or fnmatch(rel_path, pattern):
                return PolicyDecision(
                    path=rel_path,
                    allowed=False,
                    reason=f"khớp mẫu chặn {pattern!r} trong data policy",
                    matched_pattern=pattern,
                )

        if Path(rel_path).suffix.lower() in self.binary_extensions:
            return PolicyDecision(
                path=rel_path,
                allowed=False,
                reason="tệp nhị phân — không có nội dung văn bản để phân tích",
                matched_pattern=Path(rel_path).suffix.lower(),
            )

        if size_bytes is not None and size_bytes > self.max_file_bytes:
            return PolicyDecision(
                path=rel_path,
                allowed=False,
                reason=(
                    f"{size_bytes} byte vượt ngưỡng max_file_bytes="
                    f"{self.max_file_bytes}"
                ),
            )

        return PolicyDecision(path=rel_path, allowed=True, reason="không khớp mẫu chặn nào")

    def select(self, paths: Iterable[str]) -> tuple[list[str], list[PolicyDecision]]:
        """Trả về (danh sách được gửi, TOÀN BỘ phán quyết).

        Trả cả phần bị loại chứ không chỉ phần được nhận: danh sách bị loại
        chính là mẫu số, và `manifest.json` của bước 1 pipeline cần nó để in ra
        "đã loại N tệp, vì lý do gì".
        """
        decisions = [self.decide(p) for p in paths]
        return [d.path for d in decisions if d.allowed], decisions

    # ------------------------------------------------------- lớp hiển thị

    def preview(self, text: str) -> str:
        """Bản đã che bí mật, dùng cho panel UI và trích đoạn đính evidence.

        Đây là lớp phòng thủ theo NỘI DUNG; `select()` ở trên là lớp phòng thủ
        theo TÊN TỆP.
        """
        return redact_text(text, placeholder=self.redact_placeholder).text


def _parse_allowlist(items: list[Any]) -> dict[str, str]:
    """Mỗi mục allowlist BẮT BUỘC kèm `reason` khác rỗng.

    Một ngoại lệ không có lý do viết ra là một ngoại lệ không ai dám gỡ về sau:
    không ai biết nó còn cần hay không.
    """
    out: dict[str, str] = {}
    for i, item in enumerate(items):
        if not isinstance(item, dict) or "name" not in item:
            raise ConfigError(f"allowlist_exact[{i}]", "cần mapping có khoá 'name'")
        reason = str(item.get("reason") or "").strip()
        if not reason:
            raise ConfigError(f"allowlist_exact[{i}].reason", "bắt buộc và không được rỗng")
        out[str(item["name"])] = reason
    return out


def load_policy(path: Path | str | None = None) -> DataPolicy:
    """Hàm tiện dụng cho tầng trên — giữ chỗ nạp cấu hình ở đúng một nơi."""
    return DataPolicy.load(path)
