"""ToT beam/prune chọn TẬP trục động — bản CERTUS tractable của axis_search.py.

Không gian tìm: một node là TẬP (frozenset) tên trục đã khoá — một LATTICE, không
phải cây (tới cùng một tập qua hai thứ tự chèn khác nhau là CÙNG node, thăm một
lần). Mô hình chỉ ĐỀ XUẤT ứng viên (đã qua `admit_axis`); mọi quyết định chấm điểm
là `axis_score.marginal_risk_density` (ρ), không bao giờ tự cài lại ở đây.

Luật trung tâm: thêm một trục khi ρ(node, trục) ≥ θ. Trục có ρ < θ là *dominated*
— nó vào QUARANTINE kèm `revisit_if`, KHÔNG bị xoá. Cuối mỗi vòng, mọi trục đang
quarantine được chấm lại ρ với node tốt nhất vòng đó; nếu giờ ≥ θ thì HỒI SINH.
Drop lặng một trục = một blindspot GIẢ trong báo cáo người đọc để quyết ship.

Progressive widening: rộng (`shallow_width`) ở nông, hẹp (`deep_width`) khi sâu.
Trần cứng: `m_cap` trục động, `max_nodes` node thăm. Lịch nằm ở config, không phải
hằng số (grid.yaml::search).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.core.grid.axis_admit import AdmitConfig, AxisCandidate, admit_axis
from app.core.grid.axis_score import (
    DegenerateMarginalError,
    SearchParams,
    is_dominated,
    marginal_risk_density,
    value,
)
from app.core.grid.zones import Zone

__all__ = ["QuarantineRecord", "SearchResult", "search_axes"]


@dataclass(frozen=True)
class QuarantineRecord:
    """Một trục bị coi dominated ở một tập nền cụ thể. `revisit_if` LÀ điều kiện
    hồi sinh, không phải trang trí: chấm lại ρ với node tốt nhất, ≥ θ_lưu thì
    revive. θ lưu TRÊN record (không phải θ hiện tại) để điều kiện ổn định."""

    axis: str
    members: tuple[str, ...]
    rho: float
    theta: float
    base_axes: tuple[str, ...]
    revisit_if: str = "rho_vs_best_node >= theta"


@dataclass
class SearchResult:
    locked_axes: dict[str, list[str]]
    quarantined: list[QuarantineRecord] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (axis, admit reason)
    rounds: int = 0
    nodes_visited: int = 0
    stop_reason: str = ""


def _dynamic_names(axes: Mapping[str, Sequence[str]], fixed: Sequence[str]) -> list[str]:
    return [n for n in axes if n not in fixed]


def search_axes(
    candidates: Sequence[AxisCandidate],
    *,
    fixed_axes: Mapping[str, Sequence[str]],
    rules: Sequence[Zone],
    params: SearchParams,
    admit_config: AdmitConfig,
) -> SearchResult:
    """Chọn tập trục động thêm vào `fixed_axes` để tối đa khối rủi ro trên mỗi ô mới.

    Trả về `locked_axes` = fixed ⊕ dynamic đã chọn (đây là cái LOCK — từ đây xuống
    mọi thứ tất định), kèm danh sách quarantine (trục bị loại tạm) và rejected
    (trục cổng admit từ chối hẳn, kèm lý do).
    """
    fixed_names = list(fixed_axes)
    base: dict[str, list[str]] = {k: list(v) for k, v in fixed_axes.items()}

    # Ứng viên còn sống (chưa nhận, chưa loại-hẳn). Quarantine là một pool RIÊNG có
    # thể hồi sinh vào lại đây.
    result = SearchResult(locked_axes=dict(base))
    pool: list[AxisCandidate] = list(candidates)
    quarantine: dict[str, QuarantineRecord] = {}

    # Frontier: danh sách (axes_dict, frozenset_names). Bắt đầu từ node nền.
    frontier: list[dict[str, list[str]]] = [dict(base)]
    visited: set[frozenset[str]] = {frozenset(base)}
    best = dict(base)
    depth = 0

    while True:
        if result.nodes_visited >= params.max_nodes:
            result.stop_reason = "max_nodes"
            break
        width = params.shallow_width if depth <= params.shallow_depth_limit else params.deep_width

        # Sinh mọi mở rộng hợp lệ từ frontier.
        expansions: list[tuple[float, dict[str, list[str]]]] = []
        for node in frontier:
            result.nodes_visited += 1
            dyn = _dynamic_names(node, fixed_names)
            if len(dyn) >= params.m_cap:
                continue
            for cand in pool:
                if cand.name in node:
                    continue
                adm = admit_axis(
                    cand, already_admitted=dyn, fixed_axes=fixed_names, config=admit_config
                )
                if not adm.accepted:
                    pair = (cand.name, adm.reason or "rejected")
                    if pair not in result.rejected:
                        result.rejected.append(pair)
                    continue
                try:
                    rho = marginal_risk_density(
                        node, cand.name, cand.members, rules, epsilon=params.epsilon
                    )
                except DegenerateMarginalError:
                    # Thêm trục không tạo ô mới (đơn trị trong ngữ cảnh này) — coi như
                    # loại hẳn, không quarantine: không có gì để hồi sinh.
                    pair = (cand.name, "degenerate_marginal")
                    if pair not in result.rejected:
                        result.rejected.append(pair)
                    continue
                if is_dominated(rho, theta=params.theta):
                    quarantine[cand.name] = QuarantineRecord(
                        axis=cand.name, members=tuple(cand.members), rho=rho,
                        theta=params.theta, base_axes=tuple(sorted(node)),
                    )
                    continue
                new_axes = {**node, cand.name: list(cand.members)}
                key = frozenset(new_axes)
                if key in visited:
                    continue
                expansions.append((rho, new_axes))

        # Quarantine ⇔ pool: loại trục đã quarantine khỏi pool vòng sau (tránh thử lại
        # vô hạn), giữ record để hồi sinh.
        pool = [c for c in pool if c.name not in quarantine]

        if not expansions:
            result.stop_reason = result.stop_reason or "converged"
            break

        # Xếp theo ρ giảm dần, chốt visited, lấy top-width.
        expansions.sort(key=lambda e: e[0], reverse=True)
        chosen: list[dict[str, list[str]]] = []
        for _rho, axes in expansions:
            key = frozenset(axes)
            if key in visited:
                continue
            visited.add(key)
            chosen.append(axes)
            if len(chosen) >= width:
                break

        frontier = chosen
        # best = node có V lớn nhất từng thấy (khối rủi ro cao nhất).
        for axes in chosen:
            if value(axes, rules) > value(best, rules):
                best = axes
        depth += 1
        result.rounds += 1

        # Hồi sinh: chấm lại mọi trục quarantine với node tốt nhất; ≥ θ_lưu thì revive.
        revived: list[str] = []
        for name, rec in list(quarantine.items()):
            if rec.axis in best:
                continue
            try:
                rho2 = marginal_risk_density(
                    best, rec.axis, rec.members, rules, epsilon=params.epsilon
                )
            except DegenerateMarginalError:
                continue
            if rho2 >= rec.theta:
                revived.append(name)
        for name in revived:
            rec = quarantine.pop(name)
            pool.append(AxisCandidate(
                name=rec.axis, members=rec.members, ref=f"revived::{rec.axis}", tier="derived"
            ))

    result.locked_axes = best
    result.quarantined = list(quarantine.values())
    return result
