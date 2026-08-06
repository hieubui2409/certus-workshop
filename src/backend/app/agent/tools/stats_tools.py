"""Tool thống kê.

Wilson interval là toán, nên nó là tool. Ngoài lý do "model tính sai", còn một lý
do sâu hơn: `center ≠ p̂` — numerator cộng `z²/(2n)`, nên 10/10 cho center 0.8612
chứ không phải 1.00. Đó đúng là chỗ trực giác của cả người lẫn model vỡ, và một
con số sai ở đây trông hoàn toàn hợp lý.

Phần tính nằm ở `core/stats/intervals.py` (wrapper quanh scipy/statsmodels);
file này chỉ bọc nó thành tool.
"""

from __future__ import annotations

from typing import Any

from app.agent.tools.registry import ToolSpec

__all__ = ["wilson_interval", "WILSON_INTERVAL"]


def wilson_interval(k: int, n: int, conf: float = 0.95) -> dict[str, Any]:
    """Khoảng tin cậy Wilson cho k thành công trên n phép thử."""
    # Import trễ: xem ghi chú ở registry.build_default_registry.
    from app.core.stats.intervals import interval_full

    result = dict(interval_full(k=k, n=n, conf=conf, method="wilson"))
    result["source"] = "core.stats.intervals.interval_full"
    # Số dùng để QUYẾT ĐỊNH gần như luôn là lower bound — nó trả lời "trường hợp
    # xấu nhất tệ tới đâu". Nêu thẳng ra để câu trả lời không tự chọn p̂.
    result["decision_number"] = "lower"
    return result


WILSON_INTERVAL = ToolSpec(
    name="wilson_interval",
    description=(
        "Tính khoảng tin cậy Wilson cho một tỉ lệ k/n. Bắt buộc gọi tool này mỗi khi "
        "câu trả lời có một tỉ lệ hoặc phần trăm: một tỉ lệ trần không kèm k/n và "
        "interval là claim dị dạng. Trả về {p_hat, center, lower, upper, width, conf, "
        "n, k, method, decision_number}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "k": {"type": "integer", "description": "Số lần thành công đã quan sát."},
            "n": {"type": "integer", "description": "Số phép thử ĐỘC LẬP, không phải số dòng log."},
            "conf": {
                "type": "number",
                "description": "Mức tin cậy, mặc định 0.95.",
                "default": 0.95,
            },
        },
        "required": ["k", "n"],
        "additionalProperties": False,
    },
    handler=wilson_interval,
)
