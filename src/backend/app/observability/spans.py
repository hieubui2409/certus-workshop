"""Span store nội bộ trên SQLite.

Lý do tồn tại: UI phải vẽ được cây span kiểu Langfuse mà KHÔNG bắt 1000 sinh
viên dựng một Langfuse thật. Đây là nguồn dữ liệu duy nhất mà trace viewer đọc;
langfuse và OTLP (nếu bật) là bản sao đi ra ngoài, không phải nguồn.

SQLite chứ không phải JSONL vì truy vấn ở đây là "lấy cả cây của một trace" và
"đếm số trace phân biệt" — hai câu hỏi cần chỉ mục, không cần quét tệp.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.settings import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
  span_id     TEXT PRIMARY KEY,
  trace_id    TEXT NOT NULL,
  parent_id   TEXT,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'step',
  started_at  REAL NOT NULL,
  ended_at    REAL,
  duration_ms REAL,
  status      TEXT NOT NULL DEFAULT 'ok',
  tokens_in   INTEGER,
  tokens_out  INTEGER,
  attributes  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, started_at);
"""


class SpanRow(BaseModel):
    """Một span đã lưu. Tên trường khớp hợp đồng SSE `event: span` ở
    `docs/design/sdd/00-index.md` §5."""

    span_id: str
    trace_id: str
    parent_id: str | None = None
    name: str
    kind: str = "step"
    started_at: float
    ended_at: float | None = None
    duration_ms: float | None = None
    status: str = "ok"
    tokens_in: int | None = None
    tokens_out: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanNode(SpanRow):
    """Một nút trong cây span. `depth` để UI thụt lề mà không phải tự duyệt lại."""

    depth: int = 0
    children: list["SpanNode"] = Field(default_factory=list)


class SpanStore:
    """Kho span. Một kết nối cho mỗi luồng — `sqlite3.Connection` không an toàn
    khi dùng chéo luồng, và pipeline có bước chạy trong thread pool."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._path = Path(db_path) if db_path is not None else Path(settings.db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._path))
            conn.row_factory = sqlite3.Row
            # WAL: trace viewer đọc trong khi pipeline vẫn đang ghi.
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    # -------------------------------------------------------------------- ghi

    def record(self, span: SpanRow | Any) -> None:
        """Upsert theo `span_id`: một span được ghi hai lần (lúc mở và lúc
        đóng) phải là MỘT hàng, không phải hai."""
        row = span if isinstance(span, SpanRow) else SpanRow.model_validate(span, from_attributes=True)
        duration = row.duration_ms
        if duration is None and row.ended_at is not None:
            duration = (row.ended_at - row.started_at) * 1000.0
        conn = self._connect()
        with conn:
            conn.execute(
                """
                INSERT INTO spans (span_id, trace_id, parent_id, name, kind, started_at,
                                   ended_at, duration_ms, status, tokens_in, tokens_out, attributes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(span_id) DO UPDATE SET
                    ended_at=excluded.ended_at, duration_ms=excluded.duration_ms,
                    status=excluded.status, tokens_in=excluded.tokens_in,
                    tokens_out=excluded.tokens_out, attributes=excluded.attributes
                """,
                (
                    row.span_id,
                    row.trace_id,
                    row.parent_id,
                    row.name,
                    row.kind,
                    row.started_at,
                    row.ended_at,
                    duration,
                    row.status,
                    row.tokens_in,
                    row.tokens_out,
                    json.dumps(row.attributes, ensure_ascii=False),
                ),
            )

    # ------------------------------------------------------------------- đọc

    def get_trace(self, trace_id: str) -> list[SpanRow]:
        rows = self._connect().execute(
            "SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at, span_id", (trace_id,)
        )
        return [_to_row(r) for r in rows]

    def get_span(self, span_id: str) -> SpanRow | None:
        row = self._connect().execute("SELECT * FROM spans WHERE span_id = ?", (span_id,)).fetchone()
        return _to_row(row) if row else None

    def trace_ids(self, limit: int = 50) -> list[str]:
        rows = self._connect().execute(
            "SELECT trace_id, MIN(started_at) AS t0 FROM spans "
            "GROUP BY trace_id ORDER BY t0 DESC LIMIT ?",
            (limit,),
        )
        return [r["trace_id"] for r in rows]

    def distinct_trace_count(self) -> int:
        """Số trace phân biệt trong kho.

        Tồn tại vì probe của tầng observability là "chạy MỘT lượt phân tích rồi
        đếm số trace" — con số đó phải hỏi được bằng một lời gọi chứ không phải
        bằng cách nhìn cây span bằng mắt.
        """
        row = self._connect().execute("SELECT COUNT(DISTINCT trace_id) AS n FROM spans").fetchone()
        return int(row["n"])

    def tree(self, trace_id: str) -> list[SpanNode]:
        """Dựng lại cây từ `parent_id`.

        Span có `parent_id` trỏ tới một span KHÔNG nằm trong trace này được
        nâng lên làm gốc — mồ côi thì phải nhìn thấy được trên UI, không được
        biến mất khỏi cây trong im lặng.
        """
        nodes = {r.span_id: SpanNode(**r.model_dump()) for r in self.get_trace(trace_id)}
        roots: list[SpanNode] = []
        for node in nodes.values():
            parent = nodes.get(node.parent_id) if node.parent_id else None
            if parent is None:
                roots.append(node)
            else:
                parent.children.append(node)

        def _depth(node: SpanNode, d: int) -> None:
            node.depth = d
            for child in node.children:
                _depth(child, d + 1)

        for root in roots:
            _depth(root, 0)
        return roots

    def purge_trace(self, trace_id: str) -> int:
        """Xoá một trace — cần cho TTL của payload đã lưu. Trả về số dòng xoá."""
        conn = self._connect()
        with conn:
            cur = conn.execute("DELETE FROM spans WHERE trace_id = ?", (trace_id,))
        return cur.rowcount


def _to_row(r: sqlite3.Row) -> SpanRow:
    data = dict(r)
    data["attributes"] = json.loads(data.get("attributes") or "{}")
    return SpanRow(**data)


_default_store: SpanStore | None = None


def get_store() -> SpanStore:
    """Kho dùng chung. Dựng lười vì việc mở tệp SQLite không nên xảy ra ở thời
    điểm import module."""
    global _default_store
    if _default_store is None:
        _default_store = SpanStore()
    return _default_store
