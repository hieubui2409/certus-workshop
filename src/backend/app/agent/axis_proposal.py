"""Đề xuất giữ/bỏ trục cho bước HITL chọn trục.

Vai của mô hình ở đây là ĐỀ XUẤT, không phán xử: nó chấm từng trục ứng viên (đã
khám phá tất định từ Enum) nên GIỮ hay BỎ khỏi lưới, kèm một câu lý do. Người dùng
mới là bên quyết — đúng luật "mô hình đề xuất, người phán xử" của cả hệ thống.

Best-effort CÓ CHỦ ĐÍCH: mock thiếu cassette, mô hình trả rác, JSON hỏng — mọi thứ
đó trả về None, KHÔNG ném. Bước HITL vẫn chạy được không cần đề xuất (người tự
curate); một đề xuất trống phải đọc ra được là 'chưa có đề xuất', không phải 'bỏ
hết'. Xem system-architecture §pipeline-hitl.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.agent.claims import ClaimParseError, extract_claims_json
from app.agent.context import render_prompt
from app.agent.llm import LLMClient
from app.settings import Settings, settings as default_settings

__all__ = ["propose_axes", "format_candidates"]


def format_candidates(candidates: Sequence[Mapping[str, Any]]) -> str:
    """Gói danh sách trục ứng viên thành khối chữ cho prompt (thứ tự giữ nguyên)."""
    lines: list[str] = []
    for c in candidates:
        members = ", ".join(str(m) for m in c.get("members", []))
        lines.append(f"- `{c['axis']}` ({len(c.get('members', []))} giá trị: {members}) — nguồn: {c.get('source', '?')}")
    return "\n".join(lines)


async def propose_axes(
    candidates: Sequence[Mapping[str, Any]],
    *,
    client: LLMClient | None = None,
    settings: Settings | None = None,
    prefetched_text: str | None = None,
) -> dict[str, dict[str, Any]] | None:
    """Trả `{axis: {"keep": bool, "rationale": str}}`, hoặc None nếu không có đề xuất.

    None là một câu trả lời hợp lệ: chế độ mô phỏng chưa thu cassette cho tập trục
    này, hoặc mô hình trả JSON hỏng. Người gọi diễn giải None thành proposal_source
    = "none" và vẫn cho người dùng tự chọn.

    `prefetched_text`: câu trả lời NGUYÊN VĂN mà người gọi đã stream được (đường
    SSE phát từng mẩu chữ cho người xem). Truyền vào thì hàm này chỉ PARSE, không
    gọi mô hình lần nữa — nếu không thì một lượt hiển thị phải trả giá bằng hai
    lượt gọi API, và tệ hơn: hai lượt có thể trả hai câu khác nhau, nên cái người
    dùng ĐỌC không còn là cái hệ thống DÙNG.
    """
    if not candidates:
        return None
    if prefetched_text is not None:
        raw = prefetched_text.strip()
        return _parse_verdicts(raw, candidates) if raw else None
    cfg = settings or default_settings
    cli = client or LLMClient(cfg)
    prompt = render_prompt("axis_proposal", CANDIDATES=format_candidates(candidates))
    try:
        # prefill "{" ép mô hình yếu (Haiku) mở JSON ngay, không lời dạo đầu.
        resp = await cli.complete(
            system="Bạn trả về đúng JSON theo yêu cầu, không kèm giải thích ngoài JSON.",
            messages=[{"role": "user", "content": prompt}],
            prefill="{",
        )
    except Exception:
        # cassette-miss / lỗi mạng / tool-loop — best-effort, không chặn HITL.
        return None

    raw = (resp.text or "").strip()
    if not raw:
        return None
    return _parse_verdicts(raw, candidates)


def _parse_verdicts(
    raw: str, candidates: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]] | None:
    """Đọc câu trả lời thô thành verdict theo trục. JSON hỏng ⇒ None, không ném.

    Chỗ ở DUY NHẤT của luật parse, dùng chung cho cả đường gọi-rồi-đọc lẫn đường
    stream-rồi-đọc: hai bản parse song song sẽ trôi khỏi nhau, và lúc đó cái người
    dùng thấy trên stream khác cái hệ thống ghi lại.
    """
    # Model mạnh (Opus) không nhận prefill `{` nên trả JSON bọc trong ```json…```
    # thay vì mở object trần. `extract_claims_json` đã biết moi cả hai dạng (fence
    # hoặc object đầu tiên) — dùng lại thay vì json.loads trần vốn vỡ vì một backtick.
    try:
        data = extract_claims_json(raw)
    except ClaimParseError:
        return None
    if not isinstance(data, dict):
        return None

    out: dict[str, dict[str, Any]] = {}
    valid = {c["axis"] for c in candidates}
    for axis, verdict in data.items():
        if axis not in valid or not isinstance(verdict, dict):
            continue
        out[axis] = {
            "keep": bool(verdict.get("keep", True)),
            "rationale": str(verdict.get("rationale", "")).strip() or None,
        }
    return out or None
