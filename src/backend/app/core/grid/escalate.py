"""Escalation t=2 → t=3: hai tầng lọc, hai khoá config RIÊNG BIỆT.

Tầng 1 giữ TRỤC chạm hot zone. Tầng 2 liệt kê mọi tổ hợp bậc escalation của chỉ
những trục đó, và giữ ứng viên CHỈ KHI zone match thật của chính nó đạt w >= hot_w.
Hai tầng nén ~11.400 → ~140 ô (~81×).

Neo tài liệu: research note 02 §5.3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.contracts.errors import ConfigError
from app.core.grid.cells import (
    CellKey,
    ExcludePredicate,
    cell_axes,
    enumerate_t_wise,
    load_grid_config,
    require_key,
)
from app.core.grid.zones import Zone, is_hot, match_zone

_SOURCE = "grid.yaml"


@dataclass(frozen=True)
class Degrees:
    base: int
    escalation: int


def load_degrees(*, config_dir: Path | None = None) -> Degrees:
    """Đọc HAI khoá riêng: `t_wise_degree` và `escalation_degree`.

    Gộp chúng thành một khoá là lỗi ĐÃ ĐO ĐƯỢC, không phải lo xa: với một khoá
    dùng chung ở t=2 trên một lượt chạy 4 trục, cả bốn "ứng viên escalation" đều
    đã là ô của lưới nền — bước escalate KHÔNG THÊM GÌ trong khi trông y như đã
    chạy, và báo cáo có thêm một mục xanh không tương ứng với công việc nào.
    Vì thế bậc escalation phải LỚN HƠN THẬT SỰ bậc nền, và điều đó kiểm ở đây.
    """
    cfg = load_grid_config(config_dir=config_dir)
    base = int(require_key(cfg, "t_wise_degree", source=_SOURCE))
    escalation = int(require_key(cfg, "escalation_degree", source=_SOURCE))
    if escalation <= base:
        raise ConfigError(
            "escalation_degree",
            f"escalation_degree={escalation} phải LỚN HƠN t_wise_degree={base}; "
            f"bằng nhau thì mọi ứng viên escalation đã là ô của lưới nền",
        )
    return Degrees(base=base, escalation=escalation)


def hot_axes(
    axes: Mapping[str, Sequence[str]],
    rules: Sequence[Zone],
    *,
    hot_w: float,
    base_degree: int,
    exclude: ExcludePredicate | None = None,
) -> list[str]:
    """TẦNG 1 — giữ những trục có ÍT NHẤT MỘT ô của lưới nền rơi vào hot zone.

    Đo trên ô thật chứ không đọc tên trục trong `when` của rule: một rule có thể
    kể tên một trục mà không ô nào thực sự khớp nó (giá trị đã đổi, trục đã hẹp
    lại), và khi đó trục kia là hot chỉ trên giấy.
    """
    touched: set[str] = set()
    for cell in enumerate_t_wise(axes, base_degree, exclude=exclude):
        zone = match_zone(cell_axes(cell), rules)
        if is_hot(zone, hot_w=hot_w):
            touched.update(cell[0])
    return [name for name in axes if name in touched]


def escalation_candidates(
    axes: Mapping[str, Sequence[str]],
    rules: Sequence[Zone],
    *,
    hot_w: float,
    base_degree: int,
    escalation_degree: int,
    exclude: ExcludePredicate | None = None,
) -> list[CellKey]:
    """TẦNG 2 — mọi tổ hợp bậc `escalation_degree` của CHỈ các trục hot, giữ lại
    ô mà ZONE MATCH THẬT CỦA CHÍNH NÓ đạt w >= hot_w.

    Một trục có thể chạm hot zone nói chung trong khi một BỘ GIÁ TRỊ CỤ THỂ của
    nó lại rơi vào catch-all lạnh; bộ đó không được sống sót chỉ vì họ hàng của
    nó nóng.

    KHÔNG dedup theo "cả ba cặp con đã resolved ở t=2". Làm thế là âm thầm vứt
    đúng lớp lỗi BẬC-3 THUẦN — một lỗi tương tác ba chiều vô hình ở mọi lát cắt
    từng cặp — tức chính thứ mà escalation sinh ra để bắt. Đó là một bước lùi
    chống-Goodhart cải trang thành dedup.
    """
    hot = hot_axes(
        axes, rules, hot_w=hot_w, base_degree=base_degree, exclude=exclude
    )
    hot_only = {name: list(axes[name]) for name in hot}
    survivors: list[CellKey] = []
    for cell in enumerate_t_wise(hot_only, escalation_degree, exclude=exclude):
        zone = match_zone(cell_axes(cell), rules)
        if is_hot(zone, hot_w=hot_w):
            survivors.append(cell)
    return survivors
