"""Tool đọc/đếm grid.

Đếm cell có công thức đóng `(S² − Σaᵢ²)/2` cho t=2. Model đếm tay thì với 4 trục
nhỏ vẫn đúng, với 10 trục thì sai — và sai lặng lẽ, vì mẫu số sai không ném
exception nào. Đó là lý do việc này là tool chứ không phải một câu trong prompt.

Band là DERIVED (`core/grid/project.py`), nên `read_grid` chỉ ĐỌC. Không có tool
nào ở đây ghi được grid.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.agent.tools.registry import ToolSpec

__all__ = ["count_grid_cells", "read_grid", "COUNT_GRID_CELLS", "READ_GRID"]


def count_grid_cells(axes: Mapping[str, Sequence[str]], t: int = 2) -> dict[str, Any]:
    """Đếm số cell của lưới t-wise sinh từ `axes`."""
    # Import trễ: xem ghi chú ở registry.build_default_registry.
    from app.core.grid.cells import count_t_wise

    sizes = {name: len(list(values)) for name, values in axes.items()}
    total = count_t_wise(axes, t=t)
    return {
        "count": total,
        "t": t,
        "axes": sizes,
        "source": "core.grid.cells.count_t_wise",
    }


def read_grid(grid_path: str) -> dict[str, Any]:
    """Đọc `grid.json` đã projected. Chỉ đọc, không sửa."""
    path = Path(grid_path)
    if not path.is_file():
        raise FileNotFoundError(f"không có grid tại {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    cells = data.get("cells", [])
    bands: dict[str, int] = {}
    for cell in cells:
        band = cell.get("band", "unknown")
        bands[band] = bands.get(band, 0) + 1
    return {
        "path": str(path),
        "cells_total": len(cells),
        "band_histogram": bands,
        "cells": cells,
    }


COUNT_GRID_CELLS = ToolSpec(
    name="count_grid_cells",
    description=(
        "Đếm số ô của lưới t-wise sinh từ tập axes đã khoá. Dùng tool này mỗi khi "
        "câu trả lời cần một con số về kích thước lưới hoặc về mẫu số của một tỉ lệ "
        "phủ. Trả về {count, t, axes, source}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "axes": {
                "type": "object",
                "description": "Ánh xạ tên trục -> danh sách giá trị của trục đó.",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
            "t": {
                "type": "integer",
                "description": "Bậc tổ hợp; mặc định 2 (pairwise).",
                "default": 2,
            },
        },
        "required": ["axes"],
        "additionalProperties": False,
    },
    handler=count_grid_cells,
)

READ_GRID = ToolSpec(
    name="read_grid",
    description=(
        "Đọc grid.json đã được projected và trả về danh sách ô kèm biểu đồ band. "
        "Chỉ đọc: band là giá trị suy diễn, không nhận từ bên ngoài."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "grid_path": {"type": "string", "description": "Đường dẫn tới grid.json."}
        },
        "required": ["grid_path"],
        "additionalProperties": False,
    },
    handler=read_grid,
)
