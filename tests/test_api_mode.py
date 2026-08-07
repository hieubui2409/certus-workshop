"""Công tắc chế độ LLM runtime — `GET/POST /api/mode`.

Route này gán `settings.llm_mode` cho CẢ process, nên mỗi test tự khôi phục về
giá trị ban đầu ở cuối: một test làm rò `llm_mode=live` sang test sau sẽ khiến
những test analyze chạy nhầm đường live (không cassette) và đỏ vì lý do lạc.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


@pytest.fixture
def client_restore_mode():
    original = settings.llm_mode
    try:
        yield TestClient(app)
    finally:
        settings.llm_mode = original


def test_get_mode_reports_current(client_restore_mode):
    r = client_restore_mode.get("/api/mode")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == settings.llm_mode
    assert set(body) == {"mode", "live_available", "model"}
    assert isinstance(body["live_available"], bool)


def test_post_flips_mode_globally(client_restore_mode):
    # Đổi sang live rồi đọc lại: GET phải thấy đúng giá trị vừa gán — chứng minh
    # nó gán vào singleton chung, không phải một bản sao cục bộ của request.
    r = client_restore_mode.post("/api/mode", json={"mode": "live"})
    assert r.status_code == 200
    assert r.json()["mode"] == "live"
    assert settings.llm_mode == "live"
    assert client_restore_mode.get("/api/mode").json()["mode"] == "live"

    r = client_restore_mode.post("/api/mode", json={"mode": "mock"})
    assert r.json()["mode"] == "mock"
    assert settings.llm_mode == "mock"


def test_post_rejects_record_from_toggle(client_restore_mode):
    # Công tắc CHỈ phơi mock⇄live. `record` phải bị chặn ở tầng schema (422) để
    # không ai vô ý bật ghi-đè-cassette qua UI lớp học.
    r = client_restore_mode.post("/api/mode", json={"mode": "record"})
    assert r.status_code == 422
    # Chế độ không được đổi khi payload bị từ chối.
    assert settings.llm_mode == "mock"
