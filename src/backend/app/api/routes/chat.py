"""Hội thoại multiturn có tool-use LIVE, phát qua SSE.

Đặt CẠNH `/api/analyze` (single-shot), KHÔNG thay. Chạy `ChatSession.run` — vòng lặp
tool-use thật qua `complete_with_tools` — và stream từng `ChatEvent`
(tool_use/tool_result/message/done/error) lên frontend theo thứ tự.

Mock-default: `LLMClient` phát lại cassette; cassette-miss ⇒ một sự kiện `error`
trung thực, KHÔNG sập request (xem `ChatSession.run`).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.api.deps import needs
from app.orchestrator.chat import ChatSession, ChatStore
from app.settings import settings

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    """Một lượt hỏi trong một thread. `thread_id` gom lịch sử để multiturn."""

    thread_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, principal=Depends(needs("grid:read"))):
    """Phát tiến trình hội thoại theo thời gian thực.

    `grid:read` là đủ và đúng tầng: chat chỉ ĐỌC (đếm ô, đọc coverage/grid qua tool);
    nó không chạy probe hay ghi band. Mỗi sự kiện mang `seq` để frontend bắt gói rơi.
    """
    store = ChatStore(settings=settings)
    session = ChatSession(req.thread_id, settings=settings, store=store)

    async def gen():
        try:
            async for ev in session.run(req.message):
                yield {
                    "event": ev.kind,
                    "data": json.dumps(
                        {"seq": ev.seq, "thread_id": ev.thread_id, "payload": ev.payload},
                        ensure_ascii=False,
                    ),
                }
        finally:
            store.close()

    return EventSourceResponse(gen())
