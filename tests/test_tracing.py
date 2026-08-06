"""Observability: một lượt phân tích phải để lại một dấu vết nối liền.

Cái được khoá ở đây là CƠ CHẾ: `trace_id` đi theo context chứ không truyền tay,
span store dựng lại được cây, và số trace phân biệt hỏi được bằng một lời gọi.
Chỗ nào của hệ dùng cơ chế đó (và chỗ nào chưa) là câu hỏi của tầng gọi, không
phải của tầng này.
"""

from __future__ import annotations

import pytest
from loguru import logger

from app.observability import logging as obs_logging
from app.observability import spans as spans_mod
from app.observability.spans import SpanStore
from app.observability.tracing import (
    current_trace_id,
    emit,
    llm_span,
    new_span,
    start_trace,
    step_span,
)
from app.settings import settings


@pytest.fixture()
def store(tmp_path, monkeypatch) -> SpanStore:
    """Span store riêng cho mỗi test — kho dùng chung nằm ở var/certus.sqlite3
    và test không được ghi vào đó."""
    s = SpanStore(tmp_path / "spans.sqlite3")
    monkeypatch.setattr(spans_mod, "_default_store", s)
    return s


# --------------------------------------------------------------- contextvar


def test_ngoai_trace_thi_khong_co_trace_id() -> None:
    assert current_trace_id() is None


def test_start_trace_dat_va_tra_lai_context() -> None:
    with start_trace("abc123") as tid:
        assert tid == "abc123"
        assert current_trace_id() == "abc123"
    assert current_trace_id() is None


def test_trace_long_nhau_khong_ro_ri() -> None:
    with start_trace("ngoai"):
        with start_trace("trong"):
            assert current_trace_id() == "trong"
        assert current_trace_id() == "ngoai"


def test_span_cua_buoc_lay_trace_id_tu_context() -> None:
    with start_trace("t-1"):
        a = new_span("ingest")
        b = new_span("enumerate_cells")
    assert a.trace_id == b.trace_id == "t-1"
    assert a.span_id != b.span_id


def test_span_ngoai_trace_tu_mo_mot_trace_va_giu_nguyen_no() -> None:
    """Span lẻ không được thành một trace một-span: span kế tiếp phải rơi vào
    cùng trace, nếu không cây span thành bụi."""
    a = new_span("lẻ-1")
    b = new_span("lẻ-2")
    assert a.trace_id == b.trace_id


# ------------------------------------------------------------------- cây span


def test_step_span_long_nhau_tao_ra_quan_he_cha_con(store: SpanStore) -> None:
    with start_trace("t-tree"):
        with step_span("analyze") as parent:
            with step_span("run_tests") as child:
                pass
    assert child.parent_id == parent.span_id

    roots = store.tree("t-tree")
    assert len(roots) == 1
    assert roots[0].name == "analyze"
    assert [c.name for c in roots[0].children] == ["run_tests"]
    assert roots[0].children[0].depth == 1


def test_step_span_ghi_thoi_luong_va_trang_thai(store: SpanStore) -> None:
    with start_trace("t-dur"):
        with step_span("ingest", files=3):
            pass
    row = store.get_trace("t-dur")[0]
    assert row.status == "ok"
    assert row.duration_ms is not None and row.duration_ms >= 0
    assert row.attributes["files"] == 3


def test_buoc_hong_hien_do_va_van_nem_tiep(store: SpanStore) -> None:
    with start_trace("t-err"):
        with pytest.raises(RuntimeError):
            with step_span("mutation"):
                raise RuntimeError("mutmut lỗi")
    row = store.get_trace("t-err")[0]
    assert row.status == "error"
    assert row.attributes["error"] == "RuntimeError"


def test_span_mo_coi_van_hien_ra_tren_cay(store: SpanStore) -> None:
    """parent_id trỏ ra ngoài trace ⇒ nâng lên làm gốc. Mồ côi phải NHÌN THẤY
    được, không được biến mất trong im lặng."""
    with start_trace("t-orphan"):
        parent = new_span("cha")
        orphan = new_span("con-mo-coi", parent_id="khong-ton-tai")
        emit(parent.finish())
        emit(orphan.finish())
    names = {r.name for r in store.tree("t-orphan")}
    assert names == {"cha", "con-mo-coi"}


def test_llm_span_duoc_danh_dau_kind_llm() -> None:
    span = llm_span("anthropic.messages.create")
    assert span.kind == "llm"
    assert span.name == "anthropic.messages.create"
    assert len(span.span_id) == 32


# ----------------------------------------------------------------- span store


def test_ghi_hai_lan_cung_span_id_van_la_mot_hang(store: SpanStore) -> None:
    with start_trace("t-upsert"):
        span = new_span("bước")
    emit(span)  # lúc mở
    emit(span.finish(status="ok", tokens=12))  # lúc đóng
    rows = store.get_trace("t-upsert")
    assert len(rows) == 1
    assert rows[0].attributes["tokens"] == 12


def test_dem_so_trace_phan_biet(store: SpanStore) -> None:
    for tid in ("t-a", "t-b", "t-a"):
        with start_trace(tid):
            with step_span("bước"):
                pass
    assert store.distinct_trace_count() == 2
    assert set(store.trace_ids()) == {"t-a", "t-b"}


def test_purge_trace_xoa_dung_mot_trace(store: SpanStore) -> None:
    for tid in ("t-giu", "t-xoa"):
        with start_trace(tid):
            with step_span("bước"):
                pass
    assert store.purge_trace("t-xoa") == 1
    assert store.distinct_trace_count() == 1
    assert store.get_trace("t-xoa") == []


def test_store_ben_vung_qua_lan_mo_lai(tmp_path) -> None:
    path = tmp_path / "spans.sqlite3"
    first = SpanStore(path)
    with start_trace("t-persist"):
        span = new_span("bước")
    first.record(span.finish().to_row())
    assert SpanStore(path).distinct_trace_count() == 1


# --------------------------------------------------------------------- log


def test_setup_logging_ghi_ra_tep(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")
    obs_logging.setup_logging(force=True)
    try:
        obs_logging.get_logger().info("một dòng để kiểm tra sink")
        logger.complete()
        content = (tmp_path / "logs" / "certus.log").read_text(encoding="utf-8")
        assert "một dòng để kiểm tra sink" in content
    finally:
        monkeypatch.undo()
        obs_logging.setup_logging(force=True)


def test_trace_context_gan_trace_id_vao_extra() -> None:
    """`trace_id` phải có mặt trong `extra` của bản ghi log — sink nào muốn in
    ra thì in được."""
    seen: list[dict] = []
    sink_id = logger.add(lambda m: seen.append(dict(m.record["extra"])), level="INFO")
    try:
        with obs_logging.trace_context("t-log"):
            logger.info("trong trace")
        logger.info("ngoài trace")
    finally:
        logger.remove(sink_id)

    assert seen[0].get("trace_id") == "t-log"
    assert "trace_id" not in seen[1]


def test_log_event_mang_theo_truong_co_cau_truc() -> None:
    seen: list[dict] = []
    sink_id = logger.add(lambda m: seen.append(dict(m.record["extra"])), level="INFO")
    try:
        obs_logging.log_event("INFO", "cell đã sinh", cells=17, zone="payment_critical")
    finally:
        logger.remove(sink_id)
    assert seen[0]["cells"] == 17
    assert seen[0]["zone"] == "payment_critical"


def test_log_llm_call_khong_no() -> None:
    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(m.record["message"]), level="INFO")
    try:
        obs_logging.log_llm_call("prompt thử", "trả lời thử")
    finally:
        logger.remove(sink_id)
    assert any("LLM call" in m for m in messages)
