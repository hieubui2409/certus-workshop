"""Tầng chat multiturn + tool-use LIVE — replay tất định, lịch sử thu gọn.

Không gọi API thật: dựng cassette cho từng vòng, chạy ChatSession và khẳng định:
- thứ tự sự kiện tool_use → tool_result → message → done,
- lịch sử thu gọn (user + assistant final) khiến lượt 2 tất định.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.llm import LLMClient, cassette_key, cassette_slug  # noqa: E402
from app.agent.tools.registry import ToolRegistry, ToolSpec  # noqa: E402
from app.orchestrator.chat import CHAT_SYSTEM, ChatSession, ChatStore  # noqa: E402
from app.settings import Settings  # noqa: E402


def _settings(tmp_path: Path) -> Settings:
    return Settings(llm_mode="mock", cassette_dir=tmp_path, model="claude-opus-5")


def _echo_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="echo",
            description="Trả lại đầu vào (tool giả cho test).",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=lambda **kw: {"echoed": kw, "ok": True},
        )
    )
    return reg


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _write(directory: Path, *, messages, tools, text, tool_uses, stop_reason) -> None:
    key = cassette_key(model="claude-opus-5", system=CHAT_SYSTEM, messages=messages, tools=tools)
    path = directory / cassette_slug(key, "chat")
    path.write_text(
        json.dumps(
            {
                "key": key,
                "model": "claude-opus-5",
                "request": {"system": CHAT_SYSTEM, "messages": messages, "tools": tools or []},
                "response": {
                    "text": text,
                    "chunks": [text] if text else [],
                    "tool_uses": tool_uses,
                    "stop_reason": stop_reason,
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


async def _collect(session: ChatSession, message: str):
    return [ev async for ev in session.run(message)]


def test_chat_single_turn_emits_tool_then_message(tmp_path):
    reg = _echo_registry()
    tools = reg.anthropic_schemas()
    user = [{"role": "user", "content": "Độ phủ tới đâu?"}]

    _write(tmp_path, messages=user, tools=tools, text="",
           tool_uses=[{"id": "t1", "name": "echo", "input": {"x": 7}}], stop_reason="tool_use")
    assistant = {"role": "assistant",
                 "content": [{"type": "tool_use", "id": "t1", "name": "echo", "input": {"x": 7}}]}
    tool_result = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1",
         "content": _canonical({"echoed": {"x": 7}, "ok": True})}]}
    _write(tmp_path, messages=[*user, assistant, tool_result], tools=tools,
           text="Line 94%.", tool_uses=[], stop_reason="end_turn")

    store = ChatStore(":memory:")
    session = ChatSession("th-1", settings=_settings(tmp_path), registry=reg,
                          store=store, client=LLMClient(_settings(tmp_path)))
    events = asyncio.run(_collect(session, "Độ phủ tới đâu?"))

    kinds = [e.kind for e in events]
    assert kinds == ["tool_use", "tool_result", "message", "done"]
    assert events[0].payload["name"] == "echo"
    assert events[1].payload["output"] == {"echoed": {"x": 7}, "ok": True}
    assert events[2].payload["text"] == "Line 94%."
    assert events[3].payload["tool_calls"] == 1
    # Lịch sử thu gọn: đúng 2 dòng (user + assistant final), KHÔNG có tool turn.
    assert store.history("th-1") == [
        {"role": "user", "content": "Độ phủ tới đâu?"},
        {"role": "assistant", "content": "Line 94%."},
    ]


def test_chat_second_turn_sees_history_deterministically(tmp_path):
    reg = _echo_registry()
    tools = reg.anthropic_schemas()
    store = ChatStore(":memory:")
    # Gieo sẵn lịch sử lượt 1 (thu gọn).
    store.append("th-2", "user", "Độ phủ tới đâu?")
    store.append("th-2", "assistant", "Line 94%.")

    # Lượt 2: messages = [u1, a1, u2] → end_turn, không tool.
    convo = [
        {"role": "user", "content": "Độ phủ tới đâu?"},
        {"role": "assistant", "content": "Line 94%."},
        {"role": "user", "content": "Còn phần nào chưa kiểm chứng?"},
    ]
    _write(tmp_path, messages=convo, tools=tools,
           text="Grid còn 14/17 ô chưa nhìn. [DERIVED]", tool_uses=[], stop_reason="end_turn")

    session = ChatSession("th-2", settings=_settings(tmp_path), registry=reg,
                          store=store, client=LLMClient(_settings(tmp_path)))
    events = asyncio.run(_collect(session, "Còn phần nào chưa kiểm chứng?"))

    assert [e.kind for e in events] == ["message", "done"]
    assert "14/17" in events[0].payload["text"]
    assert len(store.history("th-2")) == 4


def test_chat_cassette_miss_emits_error_not_crash(tmp_path):
    reg = _echo_registry()
    store = ChatStore(":memory:")
    session = ChatSession("th-3", settings=_settings(tmp_path), registry=reg,
                          store=store, client=LLMClient(_settings(tmp_path)))
    events = asyncio.run(_collect(session, "câu chưa từng thu"))
    assert [e.kind for e in events] == ["error"]
    assert "record" in events[0].payload["detail"]
