"""Trace của một lượt phân tích: một `trace_id` xuyên suốt mọi bước.

`trace_id` sống trong một `contextvar` chứ không truyền tay qua 8 bước của
pipeline — một tham số truyền tay là một tham số sẽ bị quên ở đúng một nhánh,
và nhánh bị quên luôn là nhánh cần nhất lúc có sự cố.

Ba đầu ra, theo đúng thứ tự ưu tiên:
  1. span store SQLite — LUÔN LUÔN. Đây là thứ trace viewer trên UI đọc.
  2. langfuse       — chỉ khi có LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY.
  3. OTLP           — chỉ khi có OTEL_EXPORTER_OTLP_ENDPOINT.

(2) và (3) import lười và nuốt lỗi CỦA RIÊNG exporter (có ghi warning): một
backend trace hỏng không được làm hỏng lượt phân tích. Đây là ngoại lệ duy nhất
của luật fail-closed ở tầng này, và phạm vi của nó đúng bằng lời gọi exporter.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator
from uuid import uuid4

from pydantic import BaseModel, Field

from app.observability.spans import SpanRow, get_store
from app.settings import settings

#: Trace hiện hành. `None` nghĩa là chưa có lượt phân tích nào đang mở.
_current_trace: ContextVar[str | None] = ContextVar("certus_trace_id", default=None)
#: Span cha hiện hành — để cây span có hình dạng, không phẳng lì.
_current_span: ContextVar[str | None] = ContextVar("certus_span_id", default=None)


class Span(BaseModel):
    """Một quãng thời gian có tên, thuộc về một trace."""

    trace_id: str
    span_id: str
    name: str
    parent_id: str | None = None
    kind: str = "step"
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None
    status: str = "ok"
    tokens_in: int | None = None
    tokens_out: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000.0

    def finish(self, status: str = "ok", **attrs: Any) -> Span:
        """Đóng span. Không tự ghi — `emit()` mới ghi, để chỗ gọi quyết định
        được thời điểm span rời khỏi tiến trình."""
        self.ended_at = time.time()
        self.status = status
        self.attributes.update(attrs)
        return self

    def to_row(self) -> SpanRow:
        return SpanRow(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_id=self.parent_id,
            name=self.name,
            kind=self.kind,
            started_at=self.started_at,
            ended_at=self.ended_at,
            duration_ms=self.duration_ms,
            status=self.status,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            attributes=self.attributes,
        )


# ------------------------------------------------------------------ trace_id


def current_trace_id() -> str | None:
    return _current_trace.get()


def current_span_id() -> str | None:
    return _current_span.get()


def new_trace_id() -> str:
    return uuid4().hex


@contextmanager
def start_trace(trace_id: str | None = None) -> Iterator[str]:
    """Mở một lượt phân tích. Mọi span tạo bên trong thuộc về trace này."""
    tid = trace_id or new_trace_id()
    # Khôi phục bằng set(prev), KHÔNG bằng reset(token). `reset` đòi token phải
    # được reset trong ĐÚNG context đã tạo nó — nhưng khi luồng có `await` thật
    # (bước diễn giải gọi LLM) chạy dưới CM này, generator bị asyncio đẩy qua
    # context khác và `reset` ném "Token was created in a different Context".
    # set(prev) không phụ thuộc provenance của token nên đúng cả khi lồng nhau
    # lẫn khi vắt qua await, và nó vá luôn rò contextvar giữa hai test.
    prev_trace = _current_trace.get()
    prev_span = _current_span.get()
    _current_trace.set(tid)
    _current_span.set(None)
    try:
        yield tid
    finally:
        _current_span.set(prev_span)
        _current_trace.set(prev_trace)


def _ensure_trace_id() -> str:
    """Lấy trace hiện hành; chưa có thì mở một cái và ĐẶT vào context.

    Đặt vào context chứ không chỉ trả về, để span kế tiếp rơi vào cùng trace —
    nếu không, mỗi span lẻ sẽ là một trace một-span và cây span thành bụi.
    """
    tid = _current_trace.get()
    if tid is None:
        tid = new_trace_id()
        _current_trace.set(tid)
    return tid


# -------------------------------------------------------------------- span


def new_span(
    name: str,
    *,
    kind: str = "step",
    parent_id: str | None = None,
    **attrs: Any,
) -> Span:
    """Span của một bước pipeline. `trace_id` lấy từ context."""
    return Span(
        trace_id=_ensure_trace_id(),
        span_id=uuid4().hex,
        name=name,
        parent_id=parent_id if parent_id is not None else _current_span.get(),
        kind=kind,
        attributes=dict(attrs),
    )


def llm_span(name: str) -> Span:
    """Span cho một lời gọi LLM.

    Tách riêng khỏi `new_span` vì lời gọi LLM là span duy nhất mang token
    count và độ trễ mạng, và nó được tạo từ bên trong client LLM chứ không từ
    thân pipeline.
    """
    return Span(trace_id=uuid4().hex, span_id=uuid4().hex, name=name, kind="llm")


@contextmanager
def step_span(name: str, **attrs: Any) -> Iterator[Span]:
    """Bọc một bước pipeline: mở span, đặt nó làm cha cho span con, đóng và ghi.

    Ngoại lệ được đánh dấu `status="error"` rồi ném tiếp — một bước hỏng phải
    hiện ĐỎ trên cây span, và vẫn phải hỏng thật với chỗ gọi.
    """
    span = new_span(name, **attrs)
    token = _current_span.set(span.span_id)
    try:
        yield span
    except Exception as exc:
        span.finish(status="error", error=type(exc).__name__)
        emit(span)
        raise
    else:
        if span.ended_at is None:
            span.finish()
        emit(span)
    finally:
        _current_span.reset(token)


# ------------------------------------------------------------------- xuất ra


def emit(span: Span) -> None:
    """Ghi span vào kho nội bộ, rồi (tuỳ chọn) đẩy ra langfuse và OTLP."""
    get_store().record(span.to_row())
    _export_langfuse(span)
    _export_otlp(span)


def langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def otlp_enabled() -> bool:
    return bool(settings.otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def _export_langfuse(span: Span) -> None:
    if not langfuse_enabled():
        return
    try:
        from langfuse import Langfuse  # import lười: không có key thì không nạp SDK

        client = _langfuse_client() or Langfuse()
        client.trace(id=span.trace_id, name=span.name).span(
            id=span.span_id,
            name=span.name,
            start_time=_dt(span.started_at),
            end_time=_dt(span.ended_at),
            metadata=span.attributes,
        )
    except Exception as exc:  # noqa: BLE001 — phạm vi đúng bằng lời gọi exporter
        _warn_exporter("langfuse", exc)


def _export_otlp(span: Span) -> None:
    if not otlp_enabled():
        return
    try:
        from opentelemetry import trace as otel_trace

        tracer = otel_trace.get_tracer("certus")
        otel_span = tracer.start_span(span.name, start_time=_ns(span.started_at))
        for key, value in span.attributes.items():
            otel_span.set_attribute(f"certus.{key}", str(value))
        otel_span.set_attribute("certus.trace_id", span.trace_id)
        otel_span.end(end_time=_ns(span.ended_at or time.time()))
    except Exception as exc:  # noqa: BLE001
        _warn_exporter("otlp", exc)


_lf_client: Any = None


def _langfuse_client() -> Any:
    global _lf_client
    if _lf_client is None and langfuse_enabled():
        from langfuse import Langfuse

        _lf_client = Langfuse()
    return _lf_client


def _warn_exporter(name: str, exc: Exception) -> None:
    from app.observability.logging import get_logger

    get_logger().warning(
        "exporter {} lỗi, span vẫn nằm trong span store: {}", name, type(exc).__name__
    )


def _dt(ts: float | None):
    if ts is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _ns(ts: float) -> int:
    return int(ts * 1_000_000_000)
