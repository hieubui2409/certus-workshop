"""Khám phá trục cho bước HITL — phơi PHÁN QUYẾT của engine ToT cho UI.

Chạy proposer đa nguồn → beam ρ, rồi trả về TỪNG trục kèm verdict (locked /
quarantined / rejected / floored), ρ, nguồn (enum/config/branch) và tier provenance.
Người học phải THẤY cái bị loại và vì sao, không chỉ cái được giữ. Endpoint này chỉ
ĐỌC; người dùng chốt bằng cách gửi `confirmed_axes` vào `/api/analyze`.

Hai chế độ theo loại repo:
- **repo mẫu** (`target`): Enum-only, `read_only=True` — tập trục cố định để cassette/
  bài giảng tất định. Panel hiện để XEM engine tỉa thế nào, không sửa.
- **repo thật** (`upload_id`): proposer đa nguồn (enum+config+branch), `read_only=False`
  — người dùng BẮT BUỘC chốt. Ở chế độ live còn kèm rationale của mô hình (advisory).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import needs
from app.api.schemas import AnalyzeRequest, AxisCandidate, AxisDiscoveryResponse
from app.core.grid.axis_admit import (
    AxisCandidate as EngineCandidate,
    load_admit_config,
)
from app.core.grid.axis_score import (
    DegenerateMarginalError,
    load_search_params,
    marginal_risk_density,
)
from app.core.grid.axis_search import search_axes
from app.core.grid.zones import load_zone_config
from app.orchestrator.pipeline import Pipeline, candidates_for, discover_axes
from app.settings import settings

router = APIRouter(prefix="/api", tags=["axes"])


class AxisDiscoveryRequest(BaseModel):
    """Đúng một trong `target`/`upload_id`, y như AnalyzeRequest."""

    target: str | None = None
    upload_id: str | None = None


async def _attach_rationale(out: list[AxisCandidate]) -> None:
    """Gắn rationale của mô hình vào từng trục — ADVISORY, best-effort.

    Chỉ chạy ở chế độ live/record (mock không có cassette cho prompt này → bỏ qua để
    không tốn một vòng cassette-miss). Mô hình KHÔNG đổi verdict — nó chỉ diễn giải;
    engine ρ vẫn là bên quyết lock. None ở bất kỳ trục nào là hợp lệ.
    """
    if settings.llm_mode == "mock":
        return
    from app.agent.axis_proposal import propose_axes

    payload = [{"axis": c.axis, "members": c.members, "source": c.source} for c in out]
    verdicts = await propose_axes(payload)
    if not verdicts:
        return
    for c in out:
        v = verdicts.get(c.axis)
        if v and v.get("rationale"):
            c.rationale = v["rationale"]


@router.post("/axes/discover", response_model=AxisDiscoveryResponse)
async def axes_discover(req: AxisDiscoveryRequest, principal=Depends(needs("grid:read"))):
    """Đề xuất tập trục cho một repo, kèm lý do giữ/loại từng trục."""
    pipe = Pipeline(settings)
    root = pipe.resolve_target(AnalyzeRequest(target=req.target, upload_id=req.upload_id))
    is_sample = bool(req.target)
    discovered = discover_axes(root)

    zone_cfg = load_zone_config()
    rules = zone_cfg.rules
    params = load_search_params()
    admit_cfg = load_admit_config()

    # Repo mẫu ⇒ Enum-only (candidates_for trả None); repo thật ⇒ đa nguồn.
    cands = candidates_for(root, discovered, is_sample=is_sample)
    if cands is None:
        cands = [
            EngineCandidate(
                name=n, members=tuple(v), ref=discovered.source.get(n, "?"),
                tier="retrieved", origin="enum",
            )
            for n, v in discovered.values.items()
        ]

    result = search_axes(
        cands, fixed_axes={}, rules=rules, params=params, admit_config=admit_cfg
    )
    locked = set(result.locked_axes)
    floored = len(locked) < 2
    engine = "floor" if floored else "tot"
    if floored:
        # Sàn: tập ENUM khám phá là mẫu số sạch (không rơi về branch asserted).
        locked = set(discovered.values)

    quar = {q.axis: q for q in result.quarantined}
    rej = {a: r for a, r in result.rejected}

    out: list[AxisCandidate] = []
    for c in cands:  # DUYỆT MỌI ứng viên (enum+config+branch), thứ tự candidate
        name = c.name
        common = dict(
            axis=name, members=list(c.members), source=c.ref,
            origin=c.origin, tier=c.tier,
        )
        if name in locked:
            if floored:
                out.append(AxisCandidate(**common, kept=True, verdict="floored", rho=None, reason=None))
            else:
                # ρ HIỂN THỊ = leave-one-out trên lưới CUỐI: đóng góp mật độ rủi ro
                # biên của trục này. Con số trung thực cho trục đã locked, KHÔNG dùng
                # ρ-từ-rỗng (có thể từng <θ trước khi trục khác kéo lên → mâu thuẫn verdict).
                base = {a: v for a, v in result.locked_axes.items() if a != name}
                try:
                    rho = marginal_risk_density(base, name, list(c.members), rules, epsilon=params.epsilon)
                except DegenerateMarginalError:
                    rho = None
                out.append(AxisCandidate(**common, kept=True, verdict="locked", rho=rho, reason=None))
        elif name in quar:
            out.append(AxisCandidate(**common, kept=False, verdict="quarantined", rho=quar[name].rho, reason=None))
        else:
            out.append(AxisCandidate(
                **common, kept=False, verdict="rejected", rho=None,
                reason=rej.get(name, "không được chọn"),
            ))

    if not is_sample:
        await _attach_rationale(out)

    kept_n = sum(1 for c in out if c.kept)
    if is_sample:
        note = (
            "Repo mẫu — tập trục CỐ ĐỊNH để cassette và bài giảng tất định. Bạn xem "
            "engine tỉa thế nào (ρ, verdict, vì sao loại từng trục) nhưng không sửa; "
            "phân tích chạy đúng tập này."
        )
    elif floored:
        note = (
            f"Zones hiện tại không mã hoá rủi ro của repo này (ρ=0 cho mọi trục), nên "
            f"engine rơi về giữ {kept_n} trục Enum. HÃY CHỐT 2–4 trục hợp lý — repo thật "
            "buộc qua bước này trước khi phân tích."
        )
    else:
        note = (
            f"Engine ToT giữ {kept_n}/{len(out)} trục theo mật độ rủi ro biên "
            f"(ρ ≥ θ={params.theta}). Xem lại rồi CHỐT — bạn là bên phán xử."
        )

    return AxisDiscoveryResponse(
        target=req.target, upload_id=req.upload_id,
        candidates=out, engine=engine, note=note, read_only=is_sample,
    )
