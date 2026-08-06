"""Sổ đăng ký tool deterministic.

`system-design.md` §6 chia vai dứt khoát: LLM được **đề xuất** và **diễn đạt**,
nó không **phán xử** và không **cấp số**. Bốn tool ở đây là đường duy nhất để
một con số đi vào câu trả lời — mỗi tool bọc một hàm đã có test riêng ở `core/`,
không tool nào ghi được gì.

Schema trả về đúng khuôn tool-use của Anthropic: `{name, description, input_schema}`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from app.contracts.errors import CertusError

__all__ = ["ToolSpec", "ToolRegistry", "ToolNotFoundError", "build_default_registry", "REGISTRY"]


class ToolNotFoundError(CertusError):
    """Model gọi một tool không có trong registry.

    Không nuốt im lặng và không tự đoán ý: tên tool lệch là một lỗi cấu hình
    prompt, và nó phải đọc ra được như một lỗi cấu hình.
    """

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(
            f"không có tool tên {name!r}; đang đăng ký: {', '.join(available) or '(rỗng)'}"
        )


@dataclass(frozen=True)
class ToolSpec:
    """Một tool: tên, mô tả, JSON schema đầu vào, và hàm thật chạy nó."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._specs:
            # Hai tool cùng tên nghĩa là một trong hai sẽ không bao giờ chạy,
            # và không có gì báo. Từ chối thay vì ghi đè.
            raise ValueError(f"tool {spec.name!r} đã được đăng ký")
        self._specs[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec:
        spec = self._specs.get(name)
        if spec is None:
            raise ToolNotFoundError(name, self.names())
        return spec

    def names(self) -> list[str]:
        return sorted(self._specs)

    def __iter__(self) -> Iterator[ToolSpec]:
        return iter(self._specs[name] for name in self.names())

    def __len__(self) -> int:
        return len(self._specs)

    def anthropic_schemas(self) -> list[dict[str, Any]]:
        """Danh sách `tools` truyền thẳng vào `messages.stream(...)`.

        Sắp theo tên để prompt cache không trượt chỉ vì thứ tự dict thay đổi.
        """
        return [spec.to_anthropic() for spec in self]

    def call(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Chạy tool. Kết quả luôn là dict để serialize thẳng vào `tool_result`."""
        return self.get(name).handler(**kwargs)


def build_default_registry() -> ToolRegistry:
    """Bốn tool của bước tổng hợp.

    Import trễ ở đây: `agent/` (tầng 3) build song song với `core/` (tầng 1–2),
    và một tool chưa dùng tới không được phép làm hỏng import của cả gói.
    """
    from app.agent.tools.coverage_tools import READ_COVERAGE
    from app.agent.tools.grid_tools import COUNT_GRID_CELLS, READ_GRID
    from app.agent.tools.stats_tools import WILSON_INTERVAL

    registry = ToolRegistry()
    for spec in (COUNT_GRID_CELLS, READ_GRID, WILSON_INTERVAL, READ_COVERAGE):
        registry.register(spec)
    return registry


REGISTRY = build_default_registry()
