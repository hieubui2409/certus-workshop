"""ToT beam/prune — lần Tree-of-Thoughts DUY NHẤT trong cả pipeline.

Không gian tìm kiếm là một LATTICE, không phải cây: node là TẬP (frozenset) tên
trục động đã khoá vào. Tới cùng một tập bằng hai thứ tự chèn khác nhau (a→b→c và
c→a→b) là CÙNG một node, thăm đúng một lần. `visited` là thứ cưỡng chế điều đó —
bỏ nó đi thì cùng một tập bị chấm nhiều lần và beam đầy bản sao của chính nó.

Neo tài liệu: research note 02 §5.2.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.contracts.errors import DegenerateMarginalError
from app.core.grid.score import (
    SearchParams,
    cells_of,
    marginal_risk_density,
    value_of,
)
from app.core.grid.zones import Zone

Node = dict[str, Any]  # {"dynamic": frozenset[str], "value": float, "cells": int}


# ─────────────────────── progressive widening & budget ───────────────────────


def beam_width_for_depth(
    depth: int, *, shallow_width: int, deep_width: int, shallow_depth_limit: int
) -> int:
    """Rộng ở nông, hẹp khi đã sâu — lịch nằm ở config, không bao giờ là hằng số
    trong harness."""
    return shallow_width if depth < shallow_depth_limit else deep_width


def select_beam(children: Sequence[Node], *, width: int) -> list[Node]:
    """Thứ tự toàn phần và tất định: value giảm dần, hoà thì so tuple tên trục
    tăng dần.

    Tie-break bằng tên là bắt buộc chứ không phải cho đẹp: hai node cùng value mà
    thứ tự phụ thuộc thứ tự chèn của dict thì hai lượt chạy cùng input cho hai
    kết quả khác nhau, và mọi so sánh trước/sau sau đó đều vô nghĩa.
    """
    return sorted(
        children, key=lambda c: (-float(c["value"]), tuple(sorted(c["dynamic"])))
    )[: max(width, 0)]


def check_budget(
    *,
    elapsed_s: float,
    max_wall_clock_s: float,
    nodes_expanded: int,
    max_nodes: int,
    tokens_used: int,
    max_tokens_total: int,
) -> str | None:
    """Tên của cap ĐẦU TIÊN chạm/vượt trần, theo thứ tự cố định
    (wall-clock → nodes → tokens), hoặc None.

    `cap <= 0` nghĩa là KHÔNG ÁP, không phải "đã cạn" — đọc nhầm chiều đó biến
    một trần chưa cấu hình thành một lần dừng ngay lập tức, và lượt chạy rỗng
    đó đọc y hệt một lượt chạy hội tụ nhanh.
    """
    if max_wall_clock_s > 0 and elapsed_s >= max_wall_clock_s:
        return "wall_clock"
    if max_nodes > 0 and nodes_expanded >= max_nodes:
        return "nodes"
    if max_tokens_total > 0 and tokens_used >= max_tokens_total:
        return "tokens"
    return None


def budget_used_fraction(
    *,
    elapsed_s: float,
    max_wall_clock_s: float,
    nodes_expanded: int,
    max_nodes: int,
    tokens_used: int,
    max_tokens_total: int,
) -> float:
    """MAX tỉ lệ đã dùng trên ba cap — cái nào gần cạn nhất thì cái đó lái việc
    thu beam. Trung bình ba cap sẽ giấu đúng cái sắp chạm trần."""
    fractions = [
        elapsed_s / max_wall_clock_s if max_wall_clock_s > 0 else 0.0,
        nodes_expanded / max_nodes if max_nodes > 0 else 0.0,
        tokens_used / max_tokens_total if max_tokens_total > 0 else 0.0,
    ]
    return max(fractions)


def resolve_beam_width(
    depth: int,
    *,
    shallow_width: int,
    deep_width: int,
    shallow_depth_limit: int,
    used_fraction: float,
    greedy_threshold_fraction: float,
) -> int:
    """Vượt ngưỡng greedy thì beam thu về ĐÚNG MỘT, BẤT KỂ lịch độ sâu — chế độ
    greedy anytime, giữ nguyên best-so-far."""
    if used_fraction >= greedy_threshold_fraction:
        return 1
    return beam_width_for_depth(
        depth,
        shallow_width=shallow_width,
        deep_width=deep_width,
        shallow_depth_limit=shallow_depth_limit,
    )


# ─────────────────────── quarantine, không bao giờ xoá ───────────────────────


@dataclass
class QuarantineRecord:
    """Một trục bị coi là dominated. KHÔNG bị xoá — bị CÁCH LY.

    `revisit_if` là điều kiện hồi sinh và nó LOAD-BEARING, không phải trang trí:
    cuối mỗi vòng, ρ được tính lại với node tốt nhất vòng đó, rồi điều kiện được
    ĐỌC RA KHỎI BẢN GHI và đem đối chiếu.
    """

    axis: str
    rho_at_quarantine: float
    theta: float
    round_index: int
    revisit_if: dict[str, Any]
    revived_at_round: int | None = None
    history: list[str] = field(default_factory=list)


#: Các loại điều kiện mà BẢN BUILD NÀY tự kiểm lại được. Mọi loại khác không phải
#: "chưa biết đúng hay sai" — nó là KHÔNG KIỂM ĐƯỢC, và xem §5.2 của note 02.
_CHECKABLE_CONDITIONS = frozenset({"rho_above"})


def revisit_verdict(
    record: QuarantineRecord, *, rho_now: float | None
) -> tuple[bool, str]:
    """Điều kiện hồi sinh đã thoả chưa?

    LUẬT: một điều kiện mà bản build này KHÔNG TỰ KIỂM LẠI ĐƯỢC thì KHÔNG BAO GIỜ
    được coi là đã thoả. Nó CHẶN việc hồi sinh, chứ không rơi tự do qua thành
    "thoả" — vì mặc định rơi-qua biến mọi điều kiện viết ẩu thành một cửa mở.
    """
    condition = record.revisit_if or {}
    kind = str(condition.get("type", ""))
    if kind not in _CHECKABLE_CONDITIONS:
        return False, f"điều kiện {kind!r} không kiểm lại được ⇒ giữ nguyên cách ly"
    if rho_now is None:
        return False, "ρ không tính được ở vòng này ⇒ giữ nguyên cách ly"
    threshold = float(condition["threshold"])
    if rho_now >= threshold:
        return True, f"ρ={rho_now:.6f} >= {threshold}"
    return False, f"ρ={rho_now:.6f} < {threshold}"


# ─────────────────────────────── beam search ───────────────────────────────


def _node(
    axes: Mapping[str, Sequence[str]], dynamic: frozenset[str], rules: Sequence[Zone]
) -> Node:
    return {
        "dynamic": dynamic,
        "value": value_of(axes, dynamic, rules),
        "cells": cells_of(axes, dynamic),
    }


def beam_search(
    axes: Mapping[str, Sequence[str]],
    rules: Sequence[Zone],
    *,
    params: SearchParams,
    candidates: Iterable[str] | None = None,
    seed: Iterable[str] = (),
    tokens_used: Callable[[], int] = lambda: 0,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Chạy beam trên lattice và trả về best node + toàn bộ sổ cách ly.

    Trả về cả `stop_reason`: một lượt dừng vì chạm trần budget KHÔNG được đọc
    giống một lượt dừng vì hết node để mở.
    """
    pool = list(candidates) if candidates is not None else list(axes.keys())
    start = clock()
    nodes_expanded = 0

    root = _node(axes, frozenset(seed), rules)
    visited: set[frozenset[str]] = {root["dynamic"]}
    beam: list[Node] = [root]
    best: Node = root
    quarantine: list[QuarantineRecord] = []
    stop_reason: str | None = None
    round_index = 0

    while beam and stop_reason is None:
        round_index += 1
        children: list[Node] = []

        for parent in beam:
            depth = len(parent["dynamic"])
            if depth >= params.max_dynamic_axes:
                continue
            for axis in pool:
                if axis in parent["dynamic"]:
                    continue
                child_set = frozenset(parent["dynamic"] | {axis})
                if child_set in visited:
                    # Cùng một TẬP tới bằng thứ tự khác — cùng node, thăm một lần.
                    continue

                stop_reason = check_budget(
                    elapsed_s=clock() - start,
                    max_wall_clock_s=params.max_wall_clock_s,
                    nodes_expanded=nodes_expanded,
                    max_nodes=params.max_nodes,
                    tokens_used=tokens_used(),
                    max_tokens_total=params.max_tokens_total,
                )
                if stop_reason is not None:
                    break

                rho = _rho_or_none(axes, parent["dynamic"], axis, rules, params)
                visited.add(child_set)
                nodes_expanded += 1

                if rho is None or rho < params.theta_dominated:
                    quarantine.append(
                        QuarantineRecord(
                            axis=axis,
                            rho_at_quarantine=float("nan") if rho is None else rho,
                            theta=params.theta_dominated,
                            round_index=round_index,
                            revisit_if={
                                "type": "rho_above",
                                "threshold": params.theta_dominated,
                            },
                        )
                    )
                    continue

                children.append(_node(axes, child_set, rules))
            if stop_reason is not None:
                break

        if not children:
            break

        depth = min(len(c["dynamic"]) for c in children)
        width = resolve_beam_width(
            depth,
            shallow_width=params.shallow_width,
            deep_width=params.deep_width,
            shallow_depth_limit=params.shallow_depth_limit,
            used_fraction=budget_used_fraction(
                elapsed_s=clock() - start,
                max_wall_clock_s=params.max_wall_clock_s,
                nodes_expanded=nodes_expanded,
                max_nodes=params.max_nodes,
                tokens_used=tokens_used(),
                max_tokens_total=params.max_tokens_total,
            ),
            greedy_threshold_fraction=params.greedy_threshold_fraction,
        )
        beam = select_beam(children, width=width)
        if beam and beam[0]["value"] > best["value"]:
            best = beam[0]

        _sweep_quarantine(axes, rules, params, quarantine, best, round_index)

    return {
        "best": best,
        "visited": len(visited),
        "nodes_expanded": nodes_expanded,
        "rounds": round_index,
        "quarantine": quarantine,
        "stop_reason": stop_reason,
    }


def _rho_or_none(
    axes: Mapping[str, Sequence[str]],
    subset: frozenset[str],
    axis: str,
    rules: Sequence[Zone],
    params: SearchParams,
) -> float | None:
    """ρ, hoặc None khi mẫu số suy biến.

    None ở đây KHÔNG có nghĩa "coi như 0": nó đi vào nhánh cách ly kèm ρ=NaN, nên
    trục vẫn nằm trong sổ và vẫn được xét lại mỗi vòng — mất tích mới là điều
    module này không cho phép.
    """
    try:
        return marginal_risk_density(
            axes, subset, axis, rules, epsilon=params.epsilon_marginal
        )
    except DegenerateMarginalError:
        return None


def _sweep_quarantine(
    axes: Mapping[str, Sequence[str]],
    rules: Sequence[Zone],
    params: SearchParams,
    quarantine: list[QuarantineRecord],
    best: Node,
    round_index: int,
) -> None:
    """Cuối MỖI vòng: tính lại ρ của mọi trục đang bị cách ly với node tốt nhất
    vòng đó, rồi đọc điều kiện ra khỏi bản ghi và phán."""
    for record in quarantine:
        if record.revived_at_round is not None or record.axis in best["dynamic"]:
            continue
        rho_now = _rho_or_none(axes, best["dynamic"], record.axis, rules, params)
        revive, reason = revisit_verdict(record, rho_now=rho_now)
        record.history.append(f"vòng {round_index}: {reason}")
        if revive:
            record.revived_at_round = round_index
