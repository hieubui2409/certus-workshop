"""Tool đọc kết quả đo phủ.

Đọc thẳng `coverage.xml` do `coverage.py` sinh ra. Không suy đoán, không nội suy:
nếu file không có ở đó thì đó là một sự cố của bước 4 chứ không phải một con số
để đoán.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from app.agent.tools.registry import ToolSpec

__all__ = ["read_coverage", "READ_COVERAGE"]


def read_coverage(coverage_path: str) -> dict[str, Any]:
    """Đọc coverage.xml, trả về k/n theo dòng cho toàn bộ và theo từng file."""
    path = Path(coverage_path)
    if not path.is_file():
        raise FileNotFoundError(f"không có coverage report tại {path}")

    root = ET.parse(path).getroot()
    covered_total = 0
    valid_total = 0
    files: list[dict[str, Any]] = []

    for class_node in root.iter("class"):
        lines = list(class_node.iter("line"))
        valid = len(lines)
        covered = sum(1 for line in lines if int(line.get("hits", "0")) > 0)
        covered_total += covered
        valid_total += valid
        files.append(
            {
                "filename": class_node.get("filename", ""),
                "lines_covered": covered,
                "lines_valid": valid,
            }
        )

    # Không trả `percent` khi mẫu số bằng 0: "0 dòng, phủ 0%" và "chưa đo dòng
    # nào" là hai sự cố khác nhau, và gộp lại thành 0.0 làm mất phân biệt đó.
    percent = (covered_total / valid_total) if valid_total else None
    return {
        "path": str(path),
        "lines_covered": covered_total,
        "lines_valid": valid_total,
        "line_rate": percent,
        "files": files,
        "source": "coverage.xml",
    }


READ_COVERAGE = ToolSpec(
    name="read_coverage",
    description=(
        "Đọc coverage.xml do coverage.py sinh ra và trả về số dòng đã phủ / tổng số "
        "dòng, cho toàn bộ lẫn từng file. Đây là tầng mẫu số thứ nhất (line coverage) "
        "— nó KHÔNG trả lời câu 'còn góc rủi ro nào chưa ai nhìn'. "
        "`line_rate` là null khi lines_valid = 0."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "coverage_path": {
                "type": "string",
                "description": "Đường dẫn tới coverage.xml.",
            }
        },
        "required": ["coverage_path"],
        "additionalProperties": False,
    },
    handler=read_coverage,
)
