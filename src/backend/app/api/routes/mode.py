"""Đổi chế độ LLM lúc chạy — cassette (mock) ⇄ live.

`llm_mode` vốn là biến môi trường đọc MỘT LẦN lúc khởi động. Nhưng buổi học cần
bật/tắt "gọi model thật" ngay trên UI mà không phải khởi động lại backend, nên
ta phơi nó thành một công tắc runtime.

Vì sao gán lại lúc chạy là AN TOÀN: `settings` là singleton module-level, và mọi
nơi đọc `settings.llm_mode` TẠI THỜI ĐIỂM GỌI (LLMClient được dựng mới mỗi lượt
analyze, đọc `self.settings.llm_mode` trong `stream()`), không cache lúc import.
Nên gán `settings.llm_mode = ...` ở đây lan ngay cho lượt phân tích kế tiếp.

`live` cần credentials TRONG process (khoá API, hoặc auth token của ccs/cliproxy).
Không có thì gọi model sẽ nổ `ConfigError` — nên endpoint trả kèm `live_available`
để UI biết mà mở màn hướng dẫn setup thay vì để người dùng đâm thẳng vào lỗi.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.settings import settings

router = APIRouter(prefix="/api/mode", tags=["mode"])

# Công tắc CHỈ phơi mock⇄live. `record` là việc của người thu cassette (CLI),
# không phải nút trên UI lớp học: để lọt một nút `record` ra thì có người vô ý
# bấm và ghi đè lên cassette vốn phải BẤT BIẾN cho 1000 sinh viên.
ToggleMode = Literal["mock", "live"]


def _live_available() -> bool:
    """`live` gọi được model không? = có khoá API hoặc auth token (settings HOẶC env).

    Khớp đúng điều kiện `LLMClient` dùng khi mở client thật (`agent/llm.py`): nó
    lấy `anthropic_api_key`/`anthropic_auth_token` từ settings, ngã về biến môi
    trường `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` (đường ccs/cliproxy đặt
    token vào env). Kiểm ở đây phải soi cùng nguồn, không thì UI báo "sẵn sàng"
    trong khi lượt analyze lại nổ vì thiếu khoá.
    """
    return bool(
        settings.anthropic_api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or settings.anthropic_auth_token
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )


class ModeState(BaseModel):
    """Trạng thái chế độ + việc live có gọi được không (để UI quyết định hiển thị)."""

    mode: str
    live_available: bool
    model: str


class SetModeRequest(BaseModel):
    mode: ToggleMode


@router.get("")
def get_mode() -> ModeState:
    return ModeState(
        mode=settings.llm_mode,
        live_available=_live_available(),
        model=settings.model,
    )


@router.post("")
def set_mode(req: SetModeRequest) -> ModeState:
    """Gán `llm_mode` cho cả process. KHÔNG chặn khi thiếu creds.

    Cố ý cho phép chuyển sang `live` NGAY CẢ khi `live_available=False`: lựa chọn
    UX (đã chốt) là để người dùng thấy công tắc và tự bấm, rồi UI mở màn hướng
    dẫn — chặn ở backend sẽ biến "chưa cấu hình" thành "nút chết không hiểu vì
    sao". `live_available` trả kèm để UI xử. Lượt analyze kế tiếp mới thực sự
    cần creds, và ở đó lỗi nói rõ thiếu gì.
    """
    settings.llm_mode = req.mode
    return ModeState(
        mode=settings.llm_mode,
        live_available=_live_available(),
        model=settings.model,
    )
