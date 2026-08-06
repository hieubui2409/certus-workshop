"""Sinh lưới, đếm lưới, đặt tên ô — và loader config của cả gói `core.grid`.

Cái lưới LÀ mẫu số. Mọi quyết định trong file này được cân bằng đúng một câu hỏi:
*"cách làm này có làm mẫu số co lại trong im lặng không?"* Nếu có thì nó bị từ chối,
kể cả khi cách đó nhanh hơn và trông gọn hơn.

Vì sao loader config sống ở đây: `zones`, `escalate`, `rollup`, `project` đều cần
đọc YAML kèm luật "thiếu khoá thì nêu đích danh tên khoá rồi dừng". `cells.py` là
module thấp nhất của gói và không import sibling nào, nên đây là chỗ duy nhất đặt
loader mà không tạo vòng phụ thuộc, cũng không phải nhân bản cùng mười dòng ra bốn nơi.

Neo tài liệu: research note 02 §2.2 (cell id canonical), §2.4 (code trích nguyên văn).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from allpairspy import AllPairs

from app.contracts.errors import ConfigError
from app.settings import settings

#: Một ô ở tầng này là (tên các trục, giá trị tương ứng) — CHƯA phải
#: `contracts.Cell`. `contracts.Cell` chỉ ra đời ở `project.py` sau khi có band.
#: Tách hai thứ này là có chủ ý: một ô của mẫu số tồn tại TRƯỚC và ĐỘC LẬP với
#: việc có ai đo nó hay không.
CellKey = tuple[tuple[str, ...], tuple[str, ...]]

ExcludePredicate = Callable[[CellKey], bool]


# ─────────────────────────── config loader ───────────────────────────


def config_path(name: str, *, config_dir: Path | None = None) -> Path:
    return (config_dir or settings.config_dir) / name


def load_config_file(name: str, *, config_dir: Path | None = None) -> dict[str, Any]:
    """Đọc một tệp YAML config.

    Không cache: ba tệp này vài chục dòng, còn một cache im lặng giữ lại giá trị
    cũ sau khi ai đó sửa ngưỡng là đúng loại lỗi "đọc như đã cập nhật" mà cả gói
    này tồn tại để chống.
    """
    path = config_path(name, config_dir=config_dir)
    if not path.is_file():
        raise ConfigError(name, f"không tìm thấy tệp {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(name, f"{path} phải là một mapping ở mức cao nhất")
    return data


def require_key(cfg: Mapping[str, Any], key: str, *, source: str) -> Any:
    """Lấy một khoá (hỗ trợ đường dẫn chấm) hoặc DỪNG, nêu đích danh tên khoá.

    Tuyệt đối không có tham số `default`. Một default trong code làm mất vế (i)
    và (iii) của hợp đồng config ba vế: ngưỡng thật lúc chạy không còn nằm ở chỗ
    tài liệu nói nó nằm, và không ai biết khi nào phải xem lại nó.
    """
    node: Any = cfg
    walked: list[str] = []
    for part in key.split("."):
        walked.append(part)
        if not isinstance(node, Mapping) or part not in node:
            raise ConfigError(key, f"thiếu trong {source} (dừng ở {'.'.join(walked)})")
        node = node[part]
    return node


def load_grid_config(*, config_dir: Path | None = None) -> dict[str, Any]:
    return load_config_file("grid.yaml", config_dir=config_dir)


def t_wise_degree(*, config_dir: Path | None = None) -> int:
    """Bậc của lưới NỀN. Riêng biệt với `escalation_degree` — xem escalate.py."""
    cfg = load_grid_config(config_dir=config_dir)
    return int(require_key(cfg, "t_wise_degree", source="grid.yaml"))


# ─────────────────────────── cell id ───────────────────────────


def cell_axes(cell: CellKey) -> dict[str, str]:
    names, values = cell
    return dict(zip(names, values, strict=True))


def cell_id(cell: CellKey, axis_lock: Sequence[str] | None = None) -> str:
    """`cell:<axis>=<value>|<axis>=<value>` — mọi trục của ô, theo đúng thứ tự
    axis lock giữ chúng, nối bằng `|`.

    Chuỗi đó ĐỒNG THỜI là ledger claim id, grid id và report row. Không định dạng
    nào khác: một ô mang hai tên khác nhau là hai hàng khác nhau trong sổ, và mẫu
    số vỡ ngay tại đó — nên lệch thứ tự là ValueError chứ không phải tự sắp lại.
    """
    names, values = cell
    if len(names) != len(values):
        raise ValueError(f"ô hỏng: {len(names)} trục nhưng {len(values)} giá trị")
    if axis_lock is not None:
        order = {name: i for i, name in enumerate(axis_lock)}
        missing = [n for n in names if n not in order]
        if missing:
            raise ValueError(f"trục không có trong axis lock: {missing}")
        positions = [order[n] for n in names]
        if positions != sorted(positions):
            raise ValueError(
                f"thứ tự trục {list(names)} lệch thứ tự axis lock {list(axis_lock)}"
            )
    return "cell:" + "|".join(f"{n}={v}" for n, v in zip(names, values, strict=True))


# ─────────────────────────── sinh & đếm ───────────────────────────


def count_cartesian(axes: Mapping[str, Sequence[str]]) -> int:
    """Cỡ tích đầy đủ — 1 cho zero trục (tích rỗng), không phải một ca lỗi."""
    return math.prod(len(values) for values in axes.values())


def _assignments(value_lists: Sequence[Sequence[str]]) -> Iterator[tuple[str, ...]]:
    """Mọi phép gán đầy đủ cho một tập trục đã chọn.

    Ưu tiên thư viện: với ĐÚNG hai trục, `allpairspy` phủ đủ tích Descartes và đó
    chính là miền nó sinh ra để phục vụ — đo được: 3×2 → 6/6 hàng, 2×4 → 8/8.

    Từ ba trục trở lên thì KHÔNG dùng nó: `AllPairs` sinh covering array (tập test
    rút gọn), không sinh không gian mẫu số. Đo trên 3 trục 3×2×4 với n=3 nó trả
    về 14 hàng trong khi số ô thật là 24. Nhận con số 14 ở đây chính là mẫu số co
    lại trong im lặng — đúng thứ cái lưới sinh ra để chặn.

    Trục chỉ có 1 giá trị cũng đi đường `product`: `AllPairs` từ chối tham số
    không có ít nhất hai lựa chọn, mà một trục như thế vẫn là một trục hợp lệ ở
    tầng này (bộ lọc "≥2 giá trị" là việc của admission, không phải của sinh ô).
    """
    if len(value_lists) == 2 and all(len(v) >= 2 for v in value_lists):
        for row in AllPairs([list(v) for v in value_lists], n=2):
            yield tuple(row)
        return
    yield from itertools.product(*value_lists)


def enumerate_t_wise(
    axes: Mapping[str, Sequence[str]],
    t: int,
    exclude: ExcludePredicate | None = None,
) -> Iterator[CellKey]:
    """Sinh lười từng ô t-wise. `exclude(cell) -> True` thì bỏ ô đó.

    Deterministic: thứ tự lặp bám theo thứ tự chèn của `axes`.

    `exclude` là chỗ dự án khai Ô BẤT KHẢ THI. Bản gốc có sẵn tham số này mà chưa
    nơi nào truyền vào, và hậu quả đã đo được: engine báo "chưa chạm, rủi ro TRUNG
    BÌNH" mãi mãi cho một ô không thể tồn tại — một finding vĩnh viễn đọc y như
    việc ai đó có thể làm. Bất khả thi và chưa ghé là hai chuyện khác nhau.
    """
    names = list(axes.keys())
    if t <= 0 or t > len(names):
        return
    for combo_names in itertools.combinations(names, t):
        value_lists = [axes[name] for name in combo_names]
        for values in _assignments(value_lists):
            cell: CellKey = (combo_names, values)
            if exclude is not None and exclude(cell):
                continue
            yield cell


def count_t_wise(
    axes: Mapping[str, Sequence[str]],
    t: int,
    exclude: ExcludePredicate | None = None,
) -> int:
    """Không ràng buộc: công thức đóng — tổng đối xứng sơ cấp `e_t` của cỡ các
    trục. Với t=2 rút về `(S² − Σaᵢ²)/2`.

    Chỉ đúng KHI KHÔNG có predicate loại ô. Có `exclude` nghĩa là công thức đóng
    không còn đúng, nên hàm này đếm bằng ENUMERATION THẬT — không xấp xỉ im lặng.
    Một mẫu số xấp xỉ đọc y hệt một mẫu số đo được, và đó là cả vấn đề.
    """
    if exclude is not None:
        return sum(1 for _ in enumerate_t_wise(axes, t, exclude=exclude))
    sizes = [len(values) for values in axes.values()]
    if t <= 0 or t > len(sizes):
        return 0
    return sum(math.prod(combo) for combo in itertools.combinations(sizes, t))
