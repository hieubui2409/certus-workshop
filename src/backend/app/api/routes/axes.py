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

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.deps import needs
from app.contracts.errors import CertusError
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
    """Đúng một trong `target`/`upload_id`/`local_path`, y như AnalyzeRequest."""

    target: str | None = None
    upload_id: str | None = None
    local_path: str | None = None


async def _rationale_events(out: list[AxisCandidate]) -> AsyncIterator[dict]:
    """Gắn rationale của mô hình vào từng trục, PHÁT từng mẩu chữ khi nó đến.

    ADVISORY và best-effort: mô hình KHÔNG đổi verdict — engine ρ vẫn là bên quyết
    lock. Không có rationale là hợp lệ.

    Ở mock (mặc định của lớp) KHÔNG gọi mô hình, và phải nói ra bằng `llm_skipped`
    kèm lý do. Im lặng ở đây đọc thành "mô hình không có gì để nói", còn phát lại
    token cassette thì trông như mô hình đang nghĩ thật — cả hai đều là dựng cảnh.
    Người học phải phân biệt được cái đã chạy với cái không.
    """
    if settings.llm_mode == "mock":
        yield {
            "kind": "llm_skipped",
            "reason": "đang ở chế độ cassette (mock) — bước này không gọi mô hình. "
                      "Bật live để thấy mô hình diễn giải từng trục.",
        }
        return

    from app.agent.axis_proposal import format_candidates, propose_axes
    from app.agent.context import render_prompt
    from app.agent.llm import LLMClient

    payload = [{"axis": c.axis, "members": c.members, "source": c.source} for c in out]
    yield {"kind": "step", "name": "llm_rationale", "status": "running", "axes": len(payload)}

    # Stream thô để người xem thấy mô hình ĐANG viết; text gom lại rồi mới parse
    # bằng đúng `propose_axes` — không tự parse ở đây, để một chỗ ở duy nhất giữ
    # luật "JSON hỏng ⇒ None, không ném".
    raw: list[str] = []
    try:
        cli = LLMClient(settings)
        prompt = render_prompt("axis_proposal", CANDIDATES=format_candidates(payload))
        async for chunk in cli.stream(
            system="Bạn trả về đúng JSON theo yêu cầu, không kèm giải thích ngoài JSON.",
            messages=[{"role": "user", "content": prompt}],
            prefill="{",
        ):
            raw.append(chunk)
            yield {"kind": "llm_delta", "text": chunk}
    except Exception as exc:  # noqa: BLE001 — advisory: hỏng thì mất rationale, không mất HITL
        yield {
            "kind": "llm_skipped",
            "reason": f"gọi mô hình lỗi ({type(exc).__name__}), bước chọn trục vẫn chạy: {exc}",
        }
        return

    verdicts = await propose_axes(payload, prefetched_text="".join(raw))
    if not verdicts:
        yield {
            "kind": "llm_skipped",
            "reason": "mô hình có trả lời nhưng không đọc ra được JSON hợp lệ — "
                      "bỏ phần diễn giải, verdict của engine giữ nguyên.",
        }
        return
    for c in out:
        v = verdicts.get(c.axis)
        if v and v.get("rationale"):
            c.rationale = v["rationale"]
            yield {"kind": "axis_rationale", "axis": c.axis, "rationale": c.rationale}
    yield {"kind": "step", "name": "llm_rationale", "status": "done", "got": len(verdicts)}


async def _discover_events(req: AxisDiscoveryRequest) -> AsyncIterator[dict]:
    """Chạy khám phá trục và phát TỪNG bước ngay khi nó xong.

    Đây là chỗ ở DUY NHẤT của phép tính; `/axes/discover` (REST) chỉ chạy hết
    generator này rồi lấy sự kiện `done`. Hai đường code song song sẽ trôi khỏi
    nhau, và lúc đó stream với REST nói hai sự thật khác nhau về cùng một repo.

    Sự kiện phát ra:
      step        — một giai đoạn bắt đầu/kết thúc (scan_repo, propose, admit_axes)
      axis        — verdict của MỘT trục, phát ngay khi tính xong
      llm_delta   — một mẩu chữ mô hình đang viết (chỉ live/record)
      llm_skipped — không gọi mô hình, KÈM LÝ DO (mock)
      done        — kết quả cuối, khớp từng trường với bản REST
      error       — lỗi có cấu trúc, không nuốt
    """
    pipe = Pipeline(settings)
    root = pipe.resolve_target(
        AnalyzeRequest(
            target=req.target, upload_id=req.upload_id, local_path=req.local_path
        )
    )
    is_sample = bool(req.target)

    yield {"kind": "step", "name": "scan_repo", "status": "running", "root": root.name}
    discovered = discover_axes(root)
    yield {
        "kind": "step", "name": "scan_repo", "status": "done",
        "enums_found": len(discovered.values),
        "axes": sorted(discovered.values),
    }

    zone_cfg = load_zone_config()
    rules = zone_cfg.rules
    params = load_search_params()
    admit_cfg = load_admit_config()

    # Repo mẫu ⇒ Enum-only (candidates_for trả None); repo thật ⇒ đa nguồn.
    yield {"kind": "step", "name": "propose", "status": "running", "multi_source": not is_sample}
    cands = candidates_for(root, discovered, is_sample=is_sample)
    if cands is None:
        cands = [
            EngineCandidate(
                name=n, members=tuple(v), ref=discovered.source.get(n, "?"),
                tier="retrieved", origin="enum",
            )
            for n, v in discovered.values.items()
        ]
    by_origin: dict[str, int] = {}
    for c in cands:
        by_origin[c.origin] = by_origin.get(c.origin, 0) + 1
    yield {
        "kind": "step", "name": "propose", "status": "done",
        "candidates": len(cands), "by_origin": by_origin,
    }

    yield {"kind": "step", "name": "admit_axes", "status": "running", "theta": params.theta}
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
        before = len(out)
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
        # Phát NGAY con vừa chấm — người xem thấy engine tỉa dần, không phải
        # nhìn thanh chờ rồi nhận cả bảng.
        assert len(out) == before + 1
        yield {"kind": "axis", **out[-1].model_dump()}

    yield {
        "kind": "step", "name": "admit_axes", "status": "done",
        "locked": sum(1 for c in out if c.kept), "total": len(out), "engine": engine,
    }

    if not is_sample:
        async for ev in _rationale_events(out):
            yield ev
    else:
        yield {
            "kind": "llm_skipped",
            "reason": "repo mẫu — tập trục cố định để cassette và bài giảng tất định, "
                      "không hỏi mô hình.",
        }

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

    yield {
        "kind": "done",
        **AxisDiscoveryResponse(
            target=req.target, upload_id=req.upload_id, local_path=req.local_path,
            candidates=out, engine=engine, note=note, read_only=is_sample,
        ).model_dump(),
    }


@router.post("/axes/discover", response_model=AxisDiscoveryResponse)
async def axes_discover(req: AxisDiscoveryRequest, principal=Depends(needs("grid:read"))):
    """Đề xuất tập trục cho một repo, kèm lý do giữ/loại từng trục.

    Chạy hết `_discover_events` rồi lấy đúng sự kiện `done` — cùng một phép tính
    với đường SSE, nên hai đường không thể nói hai sự thật khác nhau.
    """
    final: dict | None = None
    async for ev in _discover_events(req):
        if ev.get("kind") == "done":
            final = ev
    if final is None:  # pragma: no cover — generator luôn kết bằng `done`
        raise CertusError("khám phá trục kết thúc mà không có kết quả")
    return AxisDiscoveryResponse(**{k: v for k, v in final.items() if k != "kind"})


@router.post("/axes/discover/stream")
async def axes_discover_stream(
    req: AxisDiscoveryRequest, principal=Depends(needs("grid:read"))
):
    """Phát tiến trình khám phá trục theo thời gian thực.

    Bấm rồi chờ trong im lặng thì không phân biệt được "đang quét" với "đã treo" —
    ở repo thật bước này quét hàng nghìn tệp rồi còn hỏi mô hình. Mỗi sự kiện
    mang `seq` để frontend bắt gói rơi.
    """

    async def gen():
        seq = 0
        try:
            async for ev in _discover_events(req):
                seq += 1
                kind = ev.pop("kind")
                yield {
                    "event": kind,
                    "data": json.dumps({"seq": seq, **ev}, ensure_ascii=False, default=str),
                }
        except CertusError as exc:
            # Lỗi có cấu trúc đi ra bằng đúng dòng stream, không nuốt.
            yield {
                "event": "error",
                "data": json.dumps(
                    {"seq": seq + 1, "code": type(exc).__name__, "msg": str(exc)},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(gen())
