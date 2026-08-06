"""Cổng kết nạp trục — `admit_axis()`.

Proposer ĐỀ XUẤT, cổng này PHÁN XỬ. Tách tuyệt đối: một trục do mô hình đề xuất
không tự vào lưới được, nó phải qua đây, và đây là hàm TẤT ĐỊNH (không LLM). Cùng
tinh thần `admit.admit_axis()` của tot-grid-coverage.

Thứ tự kiểm ĐÓNG (đổi thứ tự là đổi ngữ nghĩa): provenance → degenerate →
collinear(tên) → m_cap.

- provenance: hai luật, đúng thứ tự. Tier phải NẰM TRONG `allowed_provenance_tiers`
  (nếu không: `unknown_tier` — một tier lạ không được cân bởi thứ gì, nên bị từ chối
  chứ không nhận). Chỉ khi hợp lệ mới xét độ mạnh: `asserted` không bao giờ terminal
  → `no_provenance`. Một trục chỉ được KHẲNG ĐỊNH mà không trỏ vào code đã đọc/chạy
  thì chưa đủ tư cách.
- degenerate: dưới `min_reachable_values` giá trị.
- collinear(tên): trùng tên một trục ĐÃ trong lưới (fixed hoặc đã nhận) — trùng tên
  là collinear tối đa theo định nghĩa, không cần quan sát nào để nói. THÍCH NGHI so
  với harness: harness còn một tầng collinear theo mutual information trên quan sát
  co-occurrence; CERTUS chọn trục TRƯỚC khi có ô nào được probe (ledger rỗng theo cấu
  trúc), nên MI = 0/chưa-chấm với mọi cặp — đúng ca harness tự nói là "unscored". Ta
  giữ đúng phần tất-định (đụng tên) và KHÔNG giả vờ chấm MI khi không có dữ liệu.
- m_cap: đã nhận đủ `max_dynamic_axes` (grid.yaml::search) trục động.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core.grid.cells import load_config_file, require_key

__all__ = [
    "AxisCandidate",
    "AdmissionResult",
    "AdmitConfig",
    "load_admit_config",
    "admit_axis",
]

_SOURCE = "grid.yaml"


@dataclass(frozen=True)
class AxisCandidate:
    """Một trục ứng viên do proposer đề xuất.

    `ref` là NEO bằng chứng: `file.py::EnumName` cho Enum, `config:key` cho một bề
    mặt config, `branch:file.py:line` cho một nhánh điều kiện — thứ mà provenance
    tier khai là có thật và đọc/chạy được. `tier` là một trong bốn tier.
    """

    name: str
    members: tuple[str, ...]
    ref: str
    tier: str
    origin: str = "enum"  # enum | config | branch — nguồn proposer tìm ra


@dataclass(frozen=True)
class AdmissionResult:
    """Phán quyết của cổng. `reason=None` khi nhận; ngược lại là mã từ chối
    (`unknown_tier`, `no_provenance`, `degenerate`, `collinear:<axis>`,
    `m_cap_reached`) — đọc ra được như một mã, không phải một câu tự do."""

    accepted: bool
    reason: str | None = None
    detail: str = ""
    candidate: AxisCandidate | None = None


@dataclass(frozen=True)
class AdmitConfig:
    allowed_tiers: tuple[str, ...]
    min_reachable_values: int
    m_cap: int


def load_admit_config(*, config_dir: Path | None = None) -> AdmitConfig:
    cfg = load_config_file(_SOURCE, config_dir=config_dir)
    tiers = require_key(cfg, "admit.allowed_provenance_tiers", source=_SOURCE)
    return AdmitConfig(
        allowed_tiers=tuple(str(t) for t in tiers),
        min_reachable_values=int(require_key(cfg, "admit.min_reachable_values", source=_SOURCE)),
        # m_cap sống ở search.max_dynamic_axes — MỘT chỗ ở duy nhất, không lặp.
        m_cap=int(require_key(cfg, "search.max_dynamic_axes", source=_SOURCE)),
    )


def _reject(candidate: AxisCandidate, reason: str, detail: str) -> AdmissionResult:
    return AdmissionResult(accepted=False, reason=reason, detail=detail, candidate=candidate)


def admit_axis(
    candidate: AxisCandidate,
    *,
    already_admitted: Sequence[str],
    fixed_axes: Sequence[str],
    config: AdmitConfig,
) -> AdmissionResult:
    """Quyết một ứng viên có vào lưới không. `already_admitted` là các trục ĐỘNG đã
    nhận (đếm m_cap + một nửa phạm vi trùng tên); `fixed_axes` là trục nền đã khoá
    (nửa còn lại của phạm vi trùng tên, KHÔNG đếm m_cap). Cả hai BẮT BUỘC, không
    default — một phạm vi bỏ sót fixed_axes là đúng lỗ hổng đã đóng ở harness."""
    # 1) provenance — từ vựng trước, độ mạnh sau.
    if candidate.tier not in config.allowed_tiers:
        return _reject(
            candidate, "unknown_tier",
            f"tier {candidate.tier!r} không thuộc {list(config.allowed_tiers)} — "
            "một tier lạ không được cân bởi thứ gì nên bị từ chối",
        )
    if candidate.tier == "asserted":
        return _reject(candidate, "no_provenance", "tier asserted không bao giờ terminal")

    # 2) degenerate
    if len(candidate.members) < config.min_reachable_values:
        return _reject(
            candidate, "degenerate",
            f"{len(candidate.members)} giá trị < min_reachable_values={config.min_reachable_values}",
        )

    # 3) collinear theo tên — trùng tên trong CẢ lưới (fixed ⊕ dynamic). Đặt trước
    # mọi tầng cần mẫu vì tiền đề "chưa chấm được" ở đây SAI: trùng tên là collinear
    # tối đa, không cần quan sát. Trùng tên fixed còn nguy hơn: nó sẽ âm thầm thay
    # danh sách giá trị của trục nền mà không qua freeze.
    grid_axes = [*fixed_axes, *(a for a in already_admitted if a not in fixed_axes)]
    if candidate.name in grid_axes:
        kind = "fixed" if candidate.name in fixed_axes else "dynamic"
        return _reject(
            candidate, f"collinear:{candidate.name}",
            f"đã có trục {kind} tên {candidate.name!r} trong lưới — trùng tên là "
            "collinear tối đa, không cần quan sát",
        )

    # 4) m_cap — chỉ đếm trục ĐỘNG, trục nền là xương sống không tính slot.
    if len(already_admitted) >= config.m_cap:
        return _reject(
            candidate, "m_cap_reached",
            f"{len(already_admitted)} đã nhận >= m_cap={config.m_cap}",
        )

    return AdmissionResult(accepted=True, reason=None, candidate=candidate)
