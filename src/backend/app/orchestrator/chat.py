"""Tầng chat hội thoại nhiều lượt với tool-use LIVE.

Đặt CẠNH pipeline analyze single-shot (KHÔNG thay). Chạy vòng lặp tool-use thật qua
`LLMClient.complete_with_tools`, giữ lịch sử hội thoại trong SQLite, phát `ChatEvent`.

Điểm dạy học: UI thấy đúng tool nào được gọi trong lượt. Một claim OBSERVED không kèm
tool call nào là bằng chứng sống của lỗ hổng "chỉ tool mới phong được OBSERVED".

Lịch sử lưu THU GỌN: mỗi lượt chỉ giữ câu người dùng + câu trả lời cuối (không giữ các
lượt tool_use/tool_result trong lượt). Nhờ vậy `messages` của lượt sau tất định byte →
cassette multiturn replay trúng. Xem system-architecture §7.2.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.llm import LLMClient, ToolLoopResult
from app.agent.tools.registry import REGISTRY
from app.settings import Settings, settings as default_settings

__all__ = ["ChatEvent", "ChatStore", "ChatSession", "CHAT_SYSTEM"]

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "agent" / "prompts" / "chat.md"
#: System prompt CỐ ĐỊNH — nằm trong cassette key, nên đổi nội dung là phải thu lại.
CHAT_SYSTEM = _PROMPT_PATH.read_text(encoding="utf-8")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_thread ON chat_messages(thread_id, seq);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatEvent(BaseModel):
    """Sự kiện trên dòng SSE của chat — vốn từ RIÊNG, không đụng `StreamEvent` (khoá 10
    loại của analyze). `seq` tăng đơn điệu trong một lượt để frontend bắt sự kiện rơi."""

    seq: int
    kind: Literal["message", "message_delta", "tool_use", "tool_result", "done", "error"]
    thread_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatStore:
    """Kho lịch sử hội thoại (SQLite ở `settings.db_path`)."""

    def __init__(
        self, db_path: Path | str | None = None, settings: Settings | None = None
    ) -> None:
        cfg = settings or default_settings
        path = Path(db_path) if db_path is not None else Path(cfg.db_path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "ChatStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def history(self, thread_id: str) -> list[dict[str, Any]]:
        """Lịch sử thu gọn (role/content) theo thứ tự — nạp thẳng vào messages."""
        rows = self.db.execute(
            "SELECT role, content FROM chat_messages WHERE thread_id = ? ORDER BY seq",
            (thread_id,),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def append(self, thread_id: str, role: str, content: str) -> int:
        seq = self.db.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM chat_messages WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()[0]
        self.db.execute(
            "INSERT INTO chat_messages (thread_id, seq, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (thread_id, seq, role, content, _now()),
        )
        self.db.commit()
        return int(seq)


class ChatSession:
    """Một luồng hội thoại. `run()` phát ChatEvent theo thứ tự tool_use/tool_result rồi
    message rồi done."""

    def __init__(
        self,
        thread_id: str,
        *,
        settings: Settings | None = None,
        registry: Any | None = None,
        store: ChatStore | None = None,
        client: LLMClient | None = None,
    ) -> None:
        self.thread_id = thread_id
        self.settings = settings or default_settings
        self.registry = registry if registry is not None else REGISTRY
        self.store = store
        self.client = client or LLMClient(self.settings)

    async def run(self, user_message: str) -> AsyncIterator[ChatEvent]:
        history: Sequence[Mapping[str, Any]] = self.store.history(self.thread_id) if self.store else []
        messages = [*history, {"role": "user", "content": user_message}]
        seq = 0

        # Tool-loop là một `await` (nhiều vòng gọi model), còn ta cần phát chữ NGAY
        # khi nó về. Hàng đợi nối hai nhịp đó: loop chạy như một task, mỗi mẩu chữ
        # đẩy vào queue, generator này rút ra và phát tiếp. Không có nó thì endpoint
        # tuy là SSE nhưng người dùng vẫn nhìn màn hình trống tới lúc xong cả lượt.
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _push(chunk: str) -> None:
            await queue.put(chunk)

        async def _drive() -> ToolLoopResult:
            try:
                return await self.client.complete_with_tools(
                    system=CHAT_SYSTEM, messages=messages, registry=self.registry,
                    on_chunk=_push,
                )
            finally:
                await queue.put(None)  # sentinel: hết chữ, dù xong hay lỗi

        task = asyncio.create_task(_drive())
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield ChatEvent(
                seq=seq, kind="message_delta", thread_id=self.thread_id,
                payload={"text": chunk},
            )
            seq += 1

        try:
            result = await task
        except Exception as exc:  # cassette-miss / tool-loop kiệt / tool lỗi → báo trung thực
            yield ChatEvent(
                seq=seq, kind="error", thread_id=self.thread_id, payload={"detail": str(exc)}
            )
            return

        for call in result.tool_calls:
            yield ChatEvent(
                seq=seq, kind="tool_use", thread_id=self.thread_id,
                payload={"name": call["name"], "input": call["input"]},
            )
            seq += 1
            yield ChatEvent(
                seq=seq, kind="tool_result", thread_id=self.thread_id,
                payload={"name": call["name"], "output": call["output"]},
            )
            seq += 1

        yield ChatEvent(
            seq=seq, kind="message", thread_id=self.thread_id,
            payload={"text": result.final.text},
        )
        seq += 1

        if self.store is not None:
            self.store.append(self.thread_id, "user", user_message)
            self.store.append(self.thread_id, "assistant", result.final.text)

        yield ChatEvent(
            seq=seq, kind="done", thread_id=self.thread_id,
            payload={"rounds": result.rounds, "tool_calls": len(result.tool_calls)},
        )
