"""V(A), cost(A) và mật độ rủi ro biên ρ — chấm điểm để CHỌN tập trục động.

Đây là tầng QUYẾT ĐỊNH-CHỌN-TRỤC, tách hẳn khỏi mẫu số grid t-wise: giá trị của
một TẬP trục đo trên toàn bộ tổ hợp CARTESIAN mà tập ấy sinh ra (tổng khối rủi
ro), còn độ phủ báo cáo về sau vẫn là t-wise. Hai thứ khác nhau, cố ý không gộp
— đúng như score.py của tài liệu nền (tot-grid-coverage, corpus map#7).

    V(A)      = Σ w(cell) trên mọi ô Cartesian mà A sinh ra
    cost(A)   = λ · |cells(A)|
    ρ(A, x)   = (V(A ∪ {x}) − V(A)) / (|cells(A ∪ {x})| − |cells(A)|)

Trục có ρ dưới θ là *dominated* — axis_search QUARANTINE nó, KHÔNG xoá.

Vì sao giữ cả `naive_score`/`naive_is_dominated`: đó là bug Goodhart THẬT mà ρ
sửa. Mục tiêu cũ `score(A) = V(A) − cost(A)` gần như LUÔN tăng khi thêm trục — λ
nhỏ (0.02) hiếm khi thắng nổi một mẩu value dương — nên nhánh "dominated" dựng
trên nó gần như không bao giờ bắn. ρ chuẩn hoá theo SỐ Ô MỚI, nên một trục
cardinality cao pha loãng vào zone catch-all trọng số thấp đọc đúng là dominated
dù raw value−cost vẫn leo. Hai hàm naive giữ CHỈ để so cạnh nhau; beam thật chỉ
gọi ρ.

θ, λ, ε là khoá config (`grid.yaml` phần `search`) — không bao giờ là hằng số
trong module này, đúng như `zones.blocking_w`.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.contracts.errors import CertusError
from app.core.grid.cells import count_cartesian, load_config_file, require_key
from app.core.grid.zones import Zone, match_zone

__all__ = [
    "SearchParams",
    "load_search_params",
    "DegenerateMarginalError",
    "count_cartesian",
    "iter_cartesian_cells",
    "value",
    "cost",
    "naive_score",
    "marginal_risk_density",
    "is_dominated",
    "naive_is_dominated",
]

_SOURCE = "grid.yaml"


class DegenerateMarginalError(CertusError):
    """Thêm một trục làm |cells| đổi ít hơn ε — mẫu số của ρ ~ 0, mật độ KHÔNG
    xác định, thà nổi tên còn hơn báo 0 hay ±vô cực im lặng."""


class SearchParams:
    """Bó tham số ToT đọc từ `grid.yaml::search`. Không hằng số mặc định nào
    trong code — thiếu khoá thì `require_key` nổ, nêu đích danh."""

    __slots__ = (
        "lam", "theta", "epsilon", "shallow_width", "deep_width",
        "shallow_depth_limit", "m_cap", "greedy_fraction",
        "max_wall_clock_s", "max_nodes", "max_tokens_total",
    )

    def __init__(self, search: Mapping[str, Any]) -> None:
        self.lam = float(require_key(search, "lambda_cost", source=_SOURCE))
        self.theta = float(require_key(search, "theta_dominated", source=_SOURCE))
        self.epsilon = float(require_key(search, "epsilon_marginal", source=_SOURCE))
        self.shallow_width = int(require_key(search, "shallow_width", source=_SOURCE))
        self.deep_width = int(require_key(search, "deep_width", source=_SOURCE))
        self.shallow_depth_limit = int(require_key(search, "shallow_depth_limit", source=_SOURCE))
        self.m_cap = int(require_key(search, "max_dynamic_axes", source=_SOURCE))
        self.greedy_fraction = float(require_key(search, "greedy_threshold_fraction", source=_SOURCE))
        self.max_wall_clock_s = float(require_key(search, "budget.max_wall_clock_s", source=_SOURCE))
        self.max_nodes = int(require_key(search, "budget.max_nodes", source=_SOURCE))
        self.max_tokens_total = int(require_key(search, "budget.max_tokens_total", source=_SOURCE))


def load_search_params(*, config_dir: Path | None = None) -> SearchParams:
    cfg = load_config_file(_SOURCE, config_dir=config_dir)
    search = require_key(cfg, "search", source=_SOURCE)
    if not isinstance(search, Mapping):
        raise CertusError(f"{_SOURCE}::search phải là một mapping")
    return SearchParams(search)


# ─────────────────────────── Cartesian cells ───────────────────────────


def iter_cartesian_cells(axes: Mapping[str, Sequence[str]]) -> Iterator[dict[str, str]]:
    names = list(axes)
    for combo in itertools.product(*(list(axes[n]) for n in names)):
        yield dict(zip(names, combo, strict=True))


# ──────────────────────────── V, cost, ρ ────────────────────────────


def value(axes: Mapping[str, Sequence[str]], rules: Sequence[Zone]) -> float:
    """V(A): tổng `w` của zone khớp trên mọi ô Cartesian A sinh ra. Ô không khớp
    zone nào đóng góp 0, không bao giờ nổi lỗi. `A={}` là ô rỗng — khớp catch-all
    (rule `when` rỗng) nếu có."""
    total = 0.0
    for cell in iter_cartesian_cells(axes):
        zone = match_zone(cell, rules)
        if zone is not None:
            total += float(zone["w"])
    return total


def cost(axes: Mapping[str, Sequence[str]], *, lam: float) -> float:
    """cost(A) = λ · |cells(A)|, dùng CHÍNH count_cartesian mà ρ chia — hai chỗ
    không bao giờ bất đồng về nghĩa của |cells(A)|."""
    return lam * count_cartesian(axes)


def naive_score(axes: Mapping[str, Sequence[str]], rules: Sequence[Zone], *, lam: float) -> float:
    """Mục tiêu TRƯỚC-khi-sửa: V(A) − cost(A). Giữ CHỈ để so với ρ; beam thật
    không bao giờ gọi."""
    return value(axes, rules) - cost(axes, lam=lam)


def marginal_risk_density(
    axes_a: Mapping[str, Sequence[str]],
    axis_name: str,
    axis_values: Sequence[str],
    rules: Sequence[Zone],
    *,
    epsilon: float,
) -> float:
    """ρ(A, x) = (V(A ∪ {x}) − V(A)) / (|cells(A ∪ {x})| − |cells(A)|).

    Nổi `DegenerateMarginalError` khi thêm `axis_name` đổi |cells| ít hơn ε —
    thay vì chia cho (gần) 0 rồi báo một con số vô nghĩa.
    """
    axes_x = dict(axes_a)
    axes_x[axis_name] = list(axis_values)

    cells_a = count_cartesian(axes_a)
    cells_x = count_cartesian(axes_x)
    denom = cells_x - cells_a
    if abs(denom) < epsilon:
        raise DegenerateMarginalError(
            f"thêm trục {axis_name!r} vào {sorted(axes_a)} đổi số ô đúng {denom} "
            f"(< ε={epsilon!r}) — mật độ rủi ro biên không xác định ở đây"
        )
    return (value(axes_x, rules) - value(axes_a, rules)) / denom


def is_dominated(rho: float, *, theta: float) -> bool:
    """Trục có mật độ DƯỚI θ là dominated."""
    return rho < theta


def naive_is_dominated(
    axes_a: Mapping[str, Sequence[str]],
    axis_name: str,
    axis_values: Sequence[str],
    rules: Sequence[Zone],
    *,
    lam: float,
) -> bool:
    """Bản naive của `is_dominated`: True chỉ khi naive_score GIẢM sau khi thêm
    trục. Với zone weight không âm và λ nhỏ, gần như không bao giờ True — đó
    chính là bug Goodhart mà ρ sửa."""
    axes_x = dict(axes_a)
    axes_x[axis_name] = list(axis_values)
    return naive_score(axes_x, rules, lam=lam) < naive_score(axes_a, rules, lam=lam)
