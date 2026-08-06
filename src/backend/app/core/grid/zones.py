"""Zone — chiều thứ hai của lưới: predicate trên giá trị trục, có trọng số,
first-match-wins.

`allpairspy` sinh được tổ hợp nhưng không biết gì về trọng số rủi ro, nên đây là
một trong ba chỗ của cả hệ phải tự viết (system-design §2.2).

Neo tài liệu: research note 02 §2.3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.contracts.errors import ConfigError, EmptyBlockingSetError
from app.core.grid.cells import load_config_file, require_key

#: Zone là dict thuần `{"id", "when", "w"}` — giữ nguyên hình dạng của tài liệu
#: nền vì nó đi thẳng từ YAML vào report mà không qua tầng chuyển đổi nào.
Zone = dict[str, Any]

_SOURCE = "zones.yaml"


@dataclass(frozen=True)
class ZoneConfig:
    rules: list[Zone]
    blocking_w: float
    hot_w: float


def load_zone_config(*, config_dir: Path | None = None) -> ZoneConfig:
    """Đọc zones.yaml và compile luôn — không ai được cầm rules chưa compile."""
    cfg = load_config_file(_SOURCE, config_dir=config_dir)
    blocking_w = float(require_key(cfg, "blocking_w", source=_SOURCE))
    hot_w = float(require_key(cfg, "hot_w", source=_SOURCE))
    if hot_w < blocking_w:
        raise ConfigError(
            "hot_w",
            f"hot_w={hot_w} thấp hơn blocking_w={blocking_w}; 'hot' là tập con của "
            f"'blocking', không phải một trục khác",
        )
    raw_rules = require_key(cfg, "rules", source=_SOURCE)
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, str):
        raise ConfigError("rules", f"{_SOURCE}: rules phải là một danh sách")
    return ZoneConfig(
        rules=compile_zones(list(raw_rules), blocking_w=blocking_w),
        blocking_w=blocking_w,
        hot_w=hot_w,
    )


def compile_zones(rules: Sequence[Zone], *, blocking_w: float) -> list[Zone]:
    """Kiểm hình dạng từng rule, rồi kiểm điều kiện DUY NHẤT không rule nào tự
    kiểm được: tập chặn phải khác rỗng.

    Luật B18 — *"the graded party must not be able to empty the blocking set."*
    Tập chặn rỗng là một LỖI CẤU HÌNH, không phải một kết quả tốt: hạ mọi w
    xuống dưới ngưỡng thì mọi gate xanh, và không dòng log nào nói vì sao.
    """
    compiled: list[Zone] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, Mapping):
            raise ConfigError(f"rules[{index}]", "mỗi rule phải là một mapping")
        for key in ("id", "when", "w"):
            if key not in rule:
                raise ConfigError(f"rules[{index}].{key}", f"thiếu trong {_SOURCE}")
        zone_id = str(rule["id"])
        if zone_id in seen:
            raise ConfigError(
                f"rules[{index}].id",
                f"zone id {zone_id!r} trùng — first-match-wins làm bản sau chết lặng",
            )
        seen.add(zone_id)
        when = rule["when"] or {}
        if not isinstance(when, Mapping):
            raise ConfigError(f"rules[{index}].when", "when phải là một mapping")
        compiled.append({"id": zone_id, "when": dict(when), "w": float(rule["w"])})

    if not any(zone["w"] >= blocking_w for zone in compiled):
        raise EmptyBlockingSetError(
            f"không rule nào trong {_SOURCE} chạm blocking_w={blocking_w}: "
            f"tập chặn rỗng, từ chối compile"
        )
    return compiled


def _rule_matches(when: Mapping[str, Any], axes_of_cell: Mapping[str, str]) -> bool:
    for axis, expected in when.items():
        if axis not in axes_of_cell:
            # Rule nói về một trục mà ô này không mang. Ô t=2 chỉ có 2 trục, còn
            # rule có quyền nói về trục thứ ba: nó đơn giản KHÔNG KHỚP rule này
            # và đi tiếp — không bao giờ raise.
            return False
        value = axes_of_cell[axis]
        if isinstance(expected, (list, tuple, set)):
            if value not in expected:
                return False
        elif value != expected:
            return False
    return True


def match_zone(axes_of_cell: Mapping[str, str], rules: Sequence[Zone]) -> Zone | None:
    """Duyệt `rules` THEO THỨ TỰ, trả zone đầu tiên khớp.

    Đảo hai rule cùng có thể khớp một ô thì ô đó THẬT SỰ đổi zone, đổi w, và có
    thể rời khỏi tập chặn. Thứ tự trong zones.yaml là một quyết định, không phải
    cách trình bày — nên ở đây không có sort, không có "rule cụ thể nhất thắng".
    """
    for zone in rules:
        if _rule_matches(zone.get("when") or {}, axes_of_cell):
            return zone
    return None


def is_blocking(zone: Zone | None, *, blocking_w: float) -> bool:
    """Ô không thuộc zone nào KHÔNG được coi là ngoài tập chặn.

    Trả False ở đây là mặc định "an toàn" theo hướng dễ chịu cho bên bị chấm, nên
    hàm này bắt caller xử lý `None` từ trước; xem `require_zone`.
    """
    if zone is None:
        return False
    return float(zone["w"]) >= blocking_w


def is_hot(zone: Zone | None, *, hot_w: float) -> bool:
    if zone is None:
        return False
    return float(zone["w"]) >= hot_w


def require_zone(axes_of_cell: Mapping[str, str], rules: Sequence[Zone]) -> Zone:
    """Như `match_zone` nhưng DỪNG khi không zone nào khớp.

    Một ô không có zone là một ô không có trọng số, tức một ô lặng lẽ rơi khỏi
    mọi phép tính rollup. Bảng zone phải TOÀN PHẦN; nếu rule catch-all bị ai đó
    xoá khỏi config thì phải biết ngay tại đây, không phải qua một con số nhỏ đi.
    """
    zone = match_zone(axes_of_cell, rules)
    if zone is None:
        raise ConfigError(
            "rules",
            f"không zone nào khớp ô {dict(axes_of_cell)}; bảng zone không toàn phần "
            f"(thiếu rule catch-all cuối danh sách?)",
        )
    return zone
