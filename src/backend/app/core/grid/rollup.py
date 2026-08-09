"""Hai con số của lưới.

```
RWC     = Σ_{c ∉ N/A} w(c)·band_score(band(c)) / Σ_{c ∉ N/A} w(c)   ← DIAGNOSTIC
gate(z) = min_{c ∈ z, band(c) ≠ N/A} band_score(band(c))            ← GATE, per-zone
```

`risk_weighted_coverage()` là CHỈ BÁO XU HƯỚNG để đọc, không bao giờ là đầu vào
của một quyết định dừng/phát hành. `min_per_zone()` mới là thứ một gate đọc: band
TỆ NHẤT có mặt trong TỪNG zone, dưới dạng cấu trúc per-zone — không bao giờ ép về
một trung bình, vì một trung bình cho phép một zone cao che một zone thấp ở chỗ
hoàn toàn khác.

Neo tài liệu: research note 02 §3.2, §3.3.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.contracts.errors import (
    ConfigError,
    ZoneWeightConflictError,
    ZoneWithoutScoreableCellsError,
)
from app.contracts.types import Band, Cell
from app.core.grid.cells import load_config_file, load_grid_config, require_key

_GRID_SOURCE = "grid.yaml"
_FLOOR_SOURCE = "floor.yaml"


def load_band_scores(*, config_dir: Path | None = None) -> dict[str, float]:
    """Thang điểm band là DATA trong config, không phải hằng số trong code.

    `N/A` CỐ Ý không có entry: nó bị loại khỏi cả tử lẫn mẫu, không bao giờ chấm 0.
    "Không áp dụng được" không phải "rủi ro trung bình bằng không". Thêm một hàng
    N/A vào grid.yaml là cách nhanh nhất để làm hỏng mẫu số, nên hàm này từ chối.
    """
    cfg = load_grid_config(config_dir=config_dir)
    rows = require_key(cfg, "band_scores", source=_GRID_SOURCE)
    scores: dict[str, float] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or "band" not in row or "score" not in row:
            raise ConfigError(
                f"band_scores[{index}]", f"{_GRID_SOURCE}: mỗi hàng cần band và score"
            )
        band = str(row["band"])
        if band == Band.NA.value:
            raise ConfigError(
                f"band_scores[{index}].band",
                "N/A không được có điểm: nó bị loại khỏi cả tử lẫn mẫu",
            )
        scores[band] = float(row["score"])
    return scores


def _score_of(band: Band, band_scores: Mapping[str, float]) -> float:
    key = band.value if isinstance(band, Band) else str(band)
    if key not in band_scores:
        raise ConfigError(
            f"band_scores[{key}]",
            f"band {key!r} xuất hiện trong dữ liệu nhưng không có điểm trong "
            f"{_GRID_SOURCE}; chấm bừa 0 sẽ đọc y hệt một ô thật sự tệ",
        )
    return band_scores[key]


def _zone_weight(cells: Sequence[Cell]) -> dict[str, float]:
    """Một zone có ĐÚNG MỘT trọng số. Hai ô cùng zone khai khác nhau ⇒ nổ.

    KHÔNG average, KHÔNG max, KHÔNG first-wins: đã đo được ca một ô mang w=0.9
    nằm trong zone báo w=0.1, khiến cả zone tụt xuống dưới ngưỡng chặn và thoát
    khỏi release block. Mọi cách "hoà giải" đều là chọn hộ một câu trả lời cho
    một mâu thuẫn mà con người phải xử.
    """
    weights: dict[str, float] = {}
    for cell in cells:
        known = weights.get(cell.zone_id)
        if known is None:
            weights[cell.zone_id] = float(cell.zone_w)
        elif known != float(cell.zone_w):
            raise ZoneWeightConflictError(
                f"zone {cell.zone_id!r} khai hai trọng số khác nhau: {known} và "
                f"{cell.zone_w} (ô {cell.id})"
            )
    return weights


def risk_weighted_coverage(
    cells: Iterable[Cell], band_scores: Mapping[str, float]
) -> dict[str, Any]:
    """CHỈ ĐỂ THAM KHẢO. Trả dict, không bao giờ là một float trần.

    `value` là None khi mọi ô đều bị loại — báo 0.0 ở đó là trình bày "không có
    dữ liệu" thành "đã đo và bằng không", hai thứ cần hai cách xử lý khác nhau.
    `cells_excluded_na` luôn đi kèm để người đọc THẤY phần bị loại thay vì để nó
    bị hấp thụ trong im lặng.
    """
    cells = list(cells)
    _zone_weight(cells)

    excluded_na = 0
    weight_sum = 0.0
    weighted_score = 0.0
    scored = 0
    for cell in cells:
        if cell.band is Band.NA:
            excluded_na += 1
            continue
        weight = float(cell.zone_w)
        weight_sum += weight
        weighted_score += weight * _score_of(cell.band, band_scores)
        scored += 1

    return {
        "value": (weighted_score / weight_sum) if weight_sum > 0 else None,
        "cells_total": len(cells),
        "cells_scored": scored,
        "cells_excluded_na": excluded_na,
    }


def min_per_zone(
    cells: Iterable[Cell], band_scores: Mapping[str, float]
) -> dict[str, dict[str, Any]]:
    """GATE THẬT. Trả cấu trúc PER-ZONE — không bao giờ một scalar.

    Zone mất hết ô chấm được ⇒ `ZoneWithoutScoreableCellsError`. Nếu chỉ bỏ qua,
    zone đó BIẾN MẤT khỏi chính con số mà docstring của module này gọi là THE gate:
    đã đo được ca một N/A duy nhất trên ô duy nhất của zone chặn nặng nhất (w=0.95)
    làm cả zone rời khỏi báo cáo, và lượt chạy báo PASS mà không dòng nào nói có
    một zone vừa đi mất.
    """
    cells = list(cells)
    weights = _zone_weight(cells)

    grouped: dict[str, list[Cell]] = {}
    for cell in cells:
        grouped.setdefault(cell.zone_id, []).append(cell)

    result: dict[str, dict[str, Any]] = {}
    for zone_id, zone_cells in grouped.items():
        scoreable = [c for c in zone_cells if c.band is not Band.NA]
        excluded_na = len(zone_cells) - len(scoreable)
        if not scoreable:
            raise ZoneWithoutScoreableCellsError(
                f"zone {zone_id!r} (w={weights[zone_id]}) không còn ô nào chấm được: "
                f"{excluded_na} ô N/A trên tổng {len(zone_cells)}. Từ chối trả kết "
                f"quả thiếu — zone biến mất trong im lặng là cách gate tự tắt."
            )
        worst = min(scoreable, key=lambda c: _score_of(c.band, band_scores))
        result[zone_id] = {
            "w": weights[zone_id],
            "worst_band": worst.band.value,
            "worst_score": _score_of(worst.band, band_scores),
            "worst_cell_id": worst.id,
            "cells_total": len(zone_cells),
            "cells_scored": len(scoreable),
            "cells_excluded_na": excluded_na,
        }
    return result


# ─────────────────────────── sàn cho từng zone ───────────────────────────


@dataclass(frozen=True)
class Floors:
    default_min_score: float
    zones: dict[str, dict[str, Any]]

    def for_zone(self, zone_id: str) -> tuple[float, str]:
        entry = self.zones.get(zone_id)
        if entry is None:
            return self.default_min_score, "sàn mặc định (zone không khai riêng)"
        return float(entry["min_score"]), str(entry["reason"])


def load_floors(*, config_dir: Path | None = None) -> Floors:
    """floor.yaml là tệp DUY NHẤT của gói này được sửa cả hai chiều bởi bên bị
    chấm — nên mỗi mục BẮT BUỘC kèm `reason` khác rỗng, thiếu thì dừng và giữ
    nguyên luật cũ. Một lần nới sàn không giải thích được là một lần tự chấm mình.
    """
    cfg = load_config_file(_FLOOR_SOURCE, config_dir=config_dir)
    default_min_score = float(
        require_key(cfg, "default_min_score", source=_FLOOR_SOURCE)
    )
    zones: dict[str, dict[str, Any]] = {}
    for zone_id, entry in (cfg.get("zones") or {}).items():
        if not isinstance(entry, Mapping) or "min_score" not in entry:
            raise ConfigError(f"zones.{zone_id}.min_score", f"thiếu trong {_FLOOR_SOURCE}")
        reason = str(entry.get("reason") or "").strip()
        if not reason:
            raise ConfigError(
                f"zones.{zone_id}.reason",
                f"{_FLOOR_SOURCE}: sàn ghi đè phải kèm lý do khác rỗng",
            )
        zones[str(zone_id)] = {"min_score": float(entry["min_score"]), "reason": reason}
    return Floors(default_min_score=default_min_score, zones=zones)


def evaluate_floor(
    per_zone: Mapping[str, Mapping[str, Any]], floors: Floors
) -> dict[str, dict[str, Any]]:
    """So từng zone với sàn của nó. Vẫn PER-ZONE, vẫn không scalar.

    Hàm này tồn tại để floor.yaml có người đọc: một sàn khai ra mà không cổng nào
    đọc là dữ liệu mồ côi, và nợ `O3` của tài liệu nền đúng là ca đó.
    """
    verdicts: dict[str, dict[str, Any]] = {}
    for zone_id, summary in per_zone.items():
        required, reason = floors.for_zone(zone_id)
        verdicts[zone_id] = {
            "required_min_score": required,
            "worst_score": summary["worst_score"],
            "worst_band": summary["worst_band"],
            "meets_floor": float(summary["worst_score"]) >= required,
            "reason": reason,
        }
    return verdicts


def _removed_overall_coverage_score(  # noqa: N802 — giữ tên để lịch sử đọc được
    # ĐÃ GỠ. risk_weighted_coverage là số CHẨN ĐOÁN, min_per_zone là CỔNG.
    # Trộn chúng bằng 0.7/0.3 cho phép một zone tốt che một zone tệ ở chỗ
    # hoàn toàn khác — và không ai đọc con số gộp lại biết điều đó vừa xảy ra.
    # Trọng số 0.7/0.3 cũng không đến từ đâu cả; nó chỉ trông có thẩm quyền.

    cells: Iterable[Cell], band_scores: Mapping[str, float]
) -> float:
    """Điểm tổng hợp để hiển thị trên dashboard."""
    cells = list(cells)
    rwc = risk_weighted_coverage(cells, band_scores)["value"] or 0.0
    zones = min_per_zone(cells, band_scores)
    worst = min((z["worst_score"] for z in zones.values()), default=0.0)
    return 0.7 * rwc + 0.3 * worst
