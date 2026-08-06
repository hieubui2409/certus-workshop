"""Hàm mục tiêu của axis search: V, cost, và ρ (mật độ rủi ro biên).

```
V(A)      = Σ w(cell) trên các cell Cartesian đầy đủ mà A sinh ra
cost(A)   = λ · |cells(A)|
ρ(A, x)   = ( V(A ∪ {x}) − V(A) ) / ( |cells(A ∪ {x})| − |cells(A)| )
```

Neo tài liệu: research note 02 §5.1.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.contracts.errors import DegenerateMarginalError
from app.core.grid.cells import load_grid_config, require_key
from app.core.grid.zones import Zone, match_zone

_SOURCE = "grid.yaml"


@dataclass(frozen=True)
class SearchParams:
    """Mọi tham số của ToT axis search. Không giá trị nào có default trong code —
    tất cả đến từ grid.yaml, vì mỗi ngưỡng phải mang đủ ba vế."""

    lambda_cost: float
    theta_dominated: float
    epsilon_marginal: float
    shallow_width: int
    deep_width: int
    shallow_depth_limit: int
    max_dynamic_axes: int
    greedy_threshold_fraction: float
    max_wall_clock_s: float
    max_nodes: int
    max_tokens_total: int


def load_search_params(*, config_dir: Path | None = None) -> SearchParams:
    cfg = load_grid_config(config_dir=config_dir)
    get = lambda key: require_key(cfg, key, source=_SOURCE)  # noqa: E731
    return SearchParams(
        lambda_cost=float(get("search.lambda_cost")),
        theta_dominated=float(get("search.theta_dominated")),
        epsilon_marginal=float(get("search.epsilon_marginal")),
        shallow_width=int(get("search.shallow_width")),
        deep_width=int(get("search.deep_width")),
        shallow_depth_limit=int(get("search.shallow_depth_limit")),
        max_dynamic_axes=int(get("search.max_dynamic_axes")),
        greedy_threshold_fraction=float(get("search.greedy_threshold_fraction")),
        max_wall_clock_s=float(get("search.budget.max_wall_clock_s")),
        max_nodes=int(get("search.budget.max_nodes")),
        max_tokens_total=int(get("search.budget.max_tokens_total")),
    )


def subset_axes(
    axes: Mapping[str, Sequence[str]], subset: Iterable[str]
) -> dict[str, list[str]]:
    """Lát cắt của `axes` theo `subset`, GIỮ thứ tự axis lock.

    Node của lattice là một frozenset nên nó không mang thứ tự; thứ tự phải lấy
    lại từ lock, nếu không cùng một node sẽ sinh ra hai cell id khác nhau.
    """
    wanted = set(subset)
    unknown = wanted - set(axes)
    if unknown:
        raise KeyError(f"trục không có trong axis lock: {sorted(unknown)}")
    return {name: list(values) for name, values in axes.items() if name in wanted}


def cells_of(axes: Mapping[str, Sequence[str]], subset: Iterable[str]) -> int:
    """|cells(A)| — số ô Cartesian đầy đủ mà tập trục A sinh ra."""
    sub = subset_axes(axes, subset)
    if not sub:
        return 0
    size = 1
    for values in sub.values():
        size *= len(values)
    return size


def value_of(
    axes: Mapping[str, Sequence[str]],
    subset: Iterable[str],
    rules: Sequence[Zone],
) -> float:
    """V(A) — tổng trọng số rủi ro trên mọi ô Cartesian mà A sinh ra.

    Ô không khớp zone nào đóng góp 0: nó không được âm thầm mang trọng số của
    zone gần nhất, vì như thế một cấu hình zone thủng sẽ đọc như một tập trục tốt.
    """
    sub = subset_axes(axes, subset)
    if not sub:
        return 0.0
    names = list(sub.keys())
    total = 0.0
    for values in itertools.product(*sub.values()):
        zone = match_zone(dict(zip(names, values, strict=True)), rules)
        if zone is not None:
            total += float(zone["w"])
    return total


def cost(n_cells: int, *, lambda_cost: float) -> float:
    """cost(A) = λ · |cells(A)| — tuyến tính theo số ô, đúng như tài liệu nền."""
    return lambda_cost * n_cells


def naive_score(
    axes: Mapping[str, Sequence[str]],
    subset: Iterable[str],
    rules: Sequence[Zone],
    *,
    lambda_cost: float,
) -> float:
    """V(A) − cost(A). ĐƯỢC GIỮ LẠI CÓ CHỦ Ý, và KHÔNG được dùng làm tiêu chí prune.

    Đây là một lỗi Goodhart CÓ THẬT, không phải strawman dựng lên để bác: giá trị
    này tăng gần như mọi lần thêm một trục, vì số hạng chi phí tuyến tính (λ=0.02)
    hiếm khi thắng nổi một mẩu giá trị dương, nên nhánh `dominated` xây trên nó
    về cơ bản KHÔNG BAO GIỜ BẮN. ρ chuẩn hoá theo số ô MỚI mà ứng viên thêm vào,
    nên một trục nhiều giá trị loãng hết vào zone catch-all trọng số thấp đọc ra
    `dominated` đúng như nó phải thế, dù naive_score của nó vẫn leo.

    Giữ lại để so được hai đường cong cạnh nhau; xoá đi thì mất luôn bằng chứng.
    """
    return value_of(axes, subset, rules) - cost(
        cells_of(axes, subset), lambda_cost=lambda_cost
    )


def marginal_risk_density(
    axes: Mapping[str, Sequence[str]],
    subset: Iterable[str],
    candidate: str,
    rules: Sequence[Zone],
    *,
    epsilon: float,
) -> float:
    """ρ(A, x) — bao nhiêu rủi ro MỚI trên mỗi ô MỚI mà x mang lại.

    Mẫu số nhỏ hơn `epsilon` ⇒ `DegenerateMarginalError`. Thà nổ còn hơn chia cho
    (gần) không rồi trả về một con số vô nghĩa mà downstream sẽ so với θ như thật.
    """
    base = set(subset)
    if candidate in base:
        raise ValueError(f"trục {candidate!r} đã nằm trong tập A")
    widened = base | {candidate}

    denominator = cells_of(axes, widened) - cells_of(axes, base)
    if abs(denominator) < epsilon:
        raise DegenerateMarginalError(
            f"ρ có mẫu số {denominator} < ε={epsilon} khi thêm trục {candidate!r} "
            f"vào {sorted(base)}"
        )
    numerator = value_of(axes, widened, rules) - value_of(axes, base, rules)
    return numerator / denominator
