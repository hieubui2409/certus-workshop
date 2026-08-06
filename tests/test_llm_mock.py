"""Kiểm tầng gọi model ở chế độ mock.

Khẳng định trung tâm: cassette miss PHẢI nổ. Một cassette miss im lặng đọc y hệt
một lời gọi LLM trả về rỗng, và hai thứ đó cần hai cách xử lý khác nhau.
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
from app.contracts.errors import CassetteMissError  # noqa: E402
from app.settings import Settings  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM = "Bạn là tầng diễn đạt của CERTUS."
MESSAGES = [{"role": "user", "content": "Bộ kiểm phủ tới đâu?"}]
TOOLS = [
    {
        "name": "count_grid_cells",
        "description": "Đếm ô của lưới t-wise.",
        "input_schema": {"type": "object", "properties": {}},
    }
]


def _settings(tmp_path: Path, mode: str = "mock") -> Settings:
    return Settings(llm_mode=mode, cassette_dir=tmp_path, model="claude-opus-5")


def _write_cassette(
    directory: Path, *, model: str, system: str, messages: list, tools: list | None, chunks: list[str]
) -> Path:
    key = cassette_key(model=model, system=system, messages=messages, tools=tools)
    path = directory / cassette_slug(key, "test")
    path.write_text(
        json.dumps(
            {
                "key": key,
                "model": model,
                "request": {"system": system, "messages": messages, "tools": tools or []},
                "response": {
                    "text": "".join(chunks),
                    "chunks": chunks,
                    "tool_uses": [],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


# ─────────────────────────── khoá cassette ───────────────────────────


def test_key_is_stable_across_calls():
    first = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=TOOLS)
    second = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=TOOLS)
    assert first == second
    assert len(first) == 64


def test_key_changes_with_each_of_the_four_components():
    base = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=TOOLS)

    other_model = cassette_key(model="claude-opus-4-8", system=SYSTEM, messages=MESSAGES, tools=TOOLS)
    other_system = cassette_key(model="claude-opus-5", system=SYSTEM + "!", messages=MESSAGES, tools=TOOLS)
    other_messages = cassette_key(
        model="claude-opus-5",
        system=SYSTEM,
        messages=[{"role": "user", "content": "câu khác"}],
        tools=TOOLS,
    )
    # Tool set khác nghĩa là model có bộ hành động khác, nên là một lời gọi khác.
    no_tools = cassette_key(model="claude-opus-5", system=SYSTEM, messages=MESSAGES, tools=None)

    assert len({base, other_model, other_system, other_messages, no_tools}) == 5


def test_key_ignores_dict_ordering():
    a = cassette_key(model="m", system="s", messages=[{"role": "user", "content": "x"}], tools=None)
    b = cassette_key(model="m", system="s", messages=[{"content": "x", "role": "user"}], tools=None)
    assert a == b


# ─────────────────────────── chế độ mock ───────────────────────────


def test_mock_replays_recorded_response(tmp_path):
    chunks = ["Ba tầng ", "mẫu số ", "lệch nhau."]
    _write_cassette(
        tmp_path,
        model="claude-opus-5",
        system=SYSTEM,
        messages=MESSAGES,
        tools=TOOLS,
        chunks=chunks,
    )
    client = LLMClient(_settings(tmp_path))

    response = asyncio.run(client.complete(system=SYSTEM, messages=MESSAGES, tools=TOOLS))

    assert response.text == "Ba tầng mẫu số lệch nhau."
    assert response.from_cassette is True
    assert response.stop_reason == "end_turn"
    assert response.usage["output_tokens"] == 5


def test_mock_streams_chunk_by_chunk(tmp_path):
    chunks = ["Coverage ", "94%", " · Wilson95"]
    _write_cassette(
        tmp_path,
        model="claude-opus-5",
        system=SYSTEM,
        messages=MESSAGES,
        tools=None,
        chunks=chunks,
    )
    client = LLMClient(_settings(tmp_path))

    async def drain() -> list[str]:
        return [chunk async for chunk in client.stream(system=SYSTEM, messages=MESSAGES)]

    received = asyncio.run(drain())

    assert received == chunks
    assert "".join(received) == "Coverage 94% · Wilson95"


def test_cassette_miss_raises_instead_of_returning_empty(tmp_path):
    _write_cassette(
        tmp_path,
        model="claude-opus-5",
        system=SYSTEM,
        messages=MESSAGES,
        tools=None,
        chunks=["đã ghi"],
    )
    client = LLMClient(_settings(tmp_path))

    with pytest.raises(CassetteMissError) as excinfo:
        asyncio.run(
            client.complete(
                system=SYSTEM,
                messages=[{"role": "user", "content": "câu chưa từng ghi"}],
            )
        )

    message = str(excinfo.value)
    assert "record" in message  # phải chỉ ra cách sinh cassette
    assert str(tmp_path) in message


def test_empty_cassette_dir_still_raises_not_returns_empty_text(tmp_path):
    client = LLMClient(_settings(tmp_path / "khong-ton-tai"))
    with pytest.raises(CassetteMissError):
        asyncio.run(client.complete(system=SYSTEM, messages=MESSAGES))


# ─────────────────────────── cassette đi kèm repo ───────────────────────────


def test_shipped_cassettes_are_loadable_and_keyed_by_their_own_request():
    """Mỗi cassette trong repo phải khớp với chính request nó ghi lại.

    Nếu khoá lệch khỏi phần `request`, cassette đó không bao giờ được dùng tới và
    không có gì báo — nó chỉ đơn giản là chết trong thư mục.
    """
    directory = REPO_ROOT / "fixtures" / "cassettes"
    files = sorted(directory.glob("*.json"))
    assert files, "repo phải đi kèm ít nhất một cassette"

    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        request = record["request"]
        recomputed = cassette_key(
            model=record["model"],
            system=request["system"],
            messages=request["messages"],
            tools=request.get("tools"),
        )
        assert recomputed == record["key"], f"{path.name}: khoá lệch khỏi request"
        assert "".join(record["response"]["chunks"]) == record["response"]["text"]
