"""Vòng lặp tool-use nhiều vòng (tầng chat) — replay tất định từ cassette.

Bất biến trung tâm: chuỗi call của tool-loop tất định khi replay mock. Mỗi vòng là một
`complete()` riêng (một cassette-key riêng theo `messages` lớn dần); thực thi tool tất
định + serialize tool_result canonical ⇒ messages vòng sau khớp byte ⇒ trúng cassette.

Đây là test-first cho `LLMClient.complete_with_tools()` (A1). Nó KHÔNG gọi API thật:
dựng sẵn hai cassette (vòng gọi tool → vòng kết thúc) và khẳng định loop đi đúng.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.llm import LLMClient, cassette_key, cassette_slug  # noqa: E402
from app.agent.tools.registry import ToolRegistry, ToolSpec  # noqa: E402
from app.settings import Settings  # noqa: E402

SYSTEM = "Bạn là tầng chat của CERTUS."
FIRST_USER = [{"role": "user", "content": "Độ phủ tới đâu?"}]


def _settings(tmp_path: Path) -> Settings:
    return Settings(llm_mode="mock", cassette_dir=tmp_path, model="claude-opus-5")


def _echo_registry() -> ToolRegistry:
    """Registry một tool giả tất định — trả lại chính đầu vào."""
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
    key = cassette_key(model="claude-opus-5", system=SYSTEM, messages=messages, tools=tools)
    path = directory / cassette_slug(key, "tool-loop")
    path.write_text(
        json.dumps(
            {
                "key": key,
                "model": "claude-opus-5",
                "request": {"system": SYSTEM, "messages": messages, "tools": tools or []},
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


def _seed_two_round_flow(tmp_path: Path) -> ToolRegistry:
    """Cassette #1 gọi tool echo(x=7); cassette #2 (sau tool_result) kết thúc."""
    reg = _echo_registry()
    tools = reg.anthropic_schemas()

    # Vòng 1: model gọi tool.
    tool_use = {"id": "t1", "name": "echo", "input": {"x": 7}}
    _write(
        tmp_path,
        messages=FIRST_USER,
        tools=tools,
        text="",
        tool_uses=[tool_use],
        stop_reason="tool_use",
    )

    # Dựng messages vòng 2 ĐÚNG như loop sẽ dựng (đây là hợp đồng format).
    assistant_turn = {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "t1", "name": "echo", "input": {"x": 7}}],
    }
    tool_result = {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": _canonical({"echoed": {"x": 7}, "ok": True}),
            }
        ],
    }
    round2_messages = [*FIRST_USER, assistant_turn, tool_result]

    # Vòng 2: model kết thúc.
    _write(
        tmp_path,
        messages=round2_messages,
        tools=tools,
        text="Line 94%, grid 3/17 ô.",
        tool_uses=[],
        stop_reason="end_turn",
    )
    return reg


def test_tool_loop_executes_tool_then_finishes(tmp_path):
    reg = _seed_two_round_flow(tmp_path)
    client = LLMClient(_settings(tmp_path))

    result = asyncio.run(
        client.complete_with_tools(
            system=SYSTEM, messages=FIRST_USER, registry=reg, cassette_hint="tool-loop"
        )
    )

    assert result.final.text == "Line 94%, grid 3/17 ô."
    assert result.final.stop_reason == "end_turn"
    assert result.rounds == 2
    # Đúng một tool call, đúng tên + đầu vào + đầu ra.
    assert [(c["name"], c["input"]) for c in result.tool_calls] == [("echo", {"x": 7})]
    assert result.tool_calls[0]["output"] == {"echoed": {"x": 7}, "ok": True}


def test_tool_loop_returns_immediately_when_no_tool_use(tmp_path):
    reg = _echo_registry()
    _write(
        tmp_path,
        messages=FIRST_USER,
        tools=reg.anthropic_schemas(),
        text="Không cần tool.",
        tool_uses=[],
        stop_reason="end_turn",
    )
    client = LLMClient(_settings(tmp_path))

    result = asyncio.run(
        client.complete_with_tools(system=SYSTEM, messages=FIRST_USER, registry=reg)
    )
    assert result.rounds == 1
    assert result.tool_calls == []
    assert result.final.text == "Không cần tool."


def test_tool_loop_stops_at_max_rounds(tmp_path):
    """Model cứ gọi tool mãi → loop phải dừng trung thực, không lặp vô hạn."""
    reg = _echo_registry()
    # Cassette vòng 1 luôn gọi tool; các vòng sau miss → nhưng phải chạm max_rounds trước.
    _write(
        tmp_path,
        messages=FIRST_USER,
        tools=reg.anthropic_schemas(),
        text="",
        tool_uses=[{"id": "t1", "name": "echo", "input": {"x": 7}}],
        stop_reason="tool_use",
    )
    client = LLMClient(_settings(tmp_path))

    from app.agent.llm import ToolLoopExhausted

    with pytest.raises(ToolLoopExhausted):
        asyncio.run(
            client.complete_with_tools(
                system=SYSTEM, messages=FIRST_USER, registry=reg, max_rounds=1
            )
        )
