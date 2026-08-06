"""Endpoint /api/chat/stream — dây nối, xác thực, và báo lỗi trung thực.

Không gọi API thật. Kiểm ba điều đo được:
- không token ⇒ 403 (kiểm quyền chạy TRƯỚC khi stream),
- cassette-miss ⇒ phát sự kiện `error` chứ KHÔNG sập,
- luồng có tool: seed 2 cassette (vòng gọi tool → vòng kết thúc) rồi khẳng định
  thứ tự sự kiện tool_use → tool_result → message → done trên dây SSE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.llm import cassette_key, cassette_slug  # noqa: E402
from app.agent.tools.registry import REGISTRY  # noqa: E402
from app.main import app  # noqa: E402
from app.orchestrator.chat import CHAT_SYSTEM  # noqa: E402
from app.settings import settings  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_sse_exit_event():
    """sse_starlette giữ một Event global bind vào event loop của request SSE đầu;
    TestClient tạo loop mới mỗi request nên request SSE thứ 2 nổ 'bound to a different
    event loop'. Reset về None trước mỗi test buộc nó tạo lại trên loop hiện hành."""
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    yield


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client: TestClient) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": "demo-analyst"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _events(text: str) -> list[tuple[str, dict]]:
    """Parse thân SSE thành [(event, data_json)] theo thứ tự."""
    out = []
    ev = None
    for line in text.splitlines():
        if line.startswith("event:"):
            ev = line[len("event:") :].strip()
        elif line.startswith("data:") and ev is not None:
            out.append((ev, json.loads(line[len("data:") :].strip())))
            ev = None
    return out


def test_chat_stream_requires_auth(client: TestClient) -> None:
    res = client.post("/api/chat/stream", json={"thread_id": "t", "message": "hi"})
    assert res.status_code == 403


def test_chat_stream_cassette_miss_emits_error(client: TestClient, auth) -> None:
    res = client.post(
        "/api/chat/stream",
        headers=auth,
        json={"thread_id": "api-miss", "message": "câu chưa từng thu bao giờ xyz"},
    )
    assert res.status_code == 200
    evs = _events(res.text)
    assert evs, res.text
    assert evs[-1][0] == "error"
    assert "record" in evs[-1][1]["payload"]["detail"]


def test_chat_stream_tool_flow(client: TestClient, auth, tmp_path, monkeypatch) -> None:
    """Seed cassette vào cassette_dir tạm → luồng tool_use→tool_result→message→done."""
    monkeypatch.setattr(settings, "cassette_dir", tmp_path)
    monkeypatch.setattr(settings, "llm_mode", "mock")
    # db riêng: lịch sử rỗng ⇒ messages vòng 1 khớp cassette đã seed (không dính rác thread cũ).
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "chat.db"))
    tools = REGISTRY.anthropic_schemas()
    model = settings.model

    def write(messages, text, tool_uses, stop_reason):
        key = cassette_key(model=model, system=CHAT_SYSTEM, messages=messages, tools=tools)
        (tmp_path / cassette_slug(key, "chat")).write_text(
            json.dumps(
                {
                    "key": key, "model": model,
                    "request": {"system": CHAT_SYSTEM, "messages": messages, "tools": tools},
                    "response": {"text": text, "chunks": [text] if text else [],
                                 "tool_uses": tool_uses, "stop_reason": stop_reason,
                                 "usage": {"input_tokens": 1, "output_tokens": 1}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # tool THẬT trong registry, input hợp lệ (count_grid_cells là hàm thuần, tất định).
    name = "count_grid_cells"
    tool_input = {"axes": {"pm": ["card", "cash"], "amt": ["lo", "hi"]}, "t": 2}
    tu = {"id": "c1", "name": name, "input": tool_input}
    user = [{"role": "user", "content": "Grid bao nhiêu ô?"}]
    write(user, "", [tu], "tool_use")
    output = REGISTRY.call(name, **tool_input)
    assistant = {"role": "assistant", "content": [
        {"type": "tool_use", "id": "c1", "name": name, "input": tool_input}]}
    tr = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "c1",
         "content": json.dumps(output, sort_keys=True, ensure_ascii=False)}]}
    write([*user, assistant, tr], "Grid có nhiêu đó ô.", [], "end_turn")

    res = client.post(
        "/api/chat/stream", headers=auth,
        json={"thread_id": "api-tool", "message": "Grid bao nhiêu ô?"},
    )
    assert res.status_code == 200
    kinds = [e for e, _ in _events(res.text)]
    assert kinds == ["tool_use", "tool_result", "message", "done"]
