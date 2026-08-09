"""Kiểm nạp knowledge base, chunk, xếp hạng BM25 và dựng context.

Test tự dựng kb trong `tmp_path`: `kb/` thuộc lô W5, và một test của tầng 3 không
được phụ thuộc vào thứ tự build của lô sau.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.retrieval import (  # noqa: E402
    KnowledgeBase,
    build_context,
    chunk_markdown,
    tokenize,
)
from app.settings import Settings  # noqa: E402

WCAG = """# WCAG 2.2 — tiêu chí không áp dụng

Khi đánh giá một trang với một tiêu chí thành công, phép đánh giá thực hiện trên
toàn bộ nội dung mà tiêu chí có thể áp dụng vào.

## Trường hợp không có nội dung áp dụng

Nếu không có nội dung nào mà tiêu chí áp dụng vào, thì tiêu chí đó được coi là
đã thoả mãn.
"""

ISO = """# ISO/IEC 25010 — mô hình chất lượng

Tài liệu định nghĩa tám đặc tính chất lượng sản phẩm phần mềm.

## Phạm vi

Tài liệu mô tả đặc tính và đặc tính con. Nó không quy định giá trị ngưỡng cho
bất kỳ phép đo nào.
"""

HOUSE = """# Nội quy nhà

## Ba tầng mẫu số

Line coverage, mutation score và grid coverage hiển thị cạnh nhau, không gộp.
"""


def _kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "standards").mkdir(parents=True)
    (root / "house").mkdir(parents=True)
    (root / "standards" / "wcag.md").write_text(WCAG, encoding="utf-8")
    (root / "standards" / "iso-25010.md").write_text(ISO, encoding="utf-8")
    (root / "house" / "testing-rules.md").write_text(HOUSE, encoding="utf-8")
    return root


# ─────────────────────────── tokenize ───────────────────────────


def test_tokenize_keeps_vietnamese_diacritics():
    assert tokenize("Độ phủ 94%") == ["độ", "phủ", "94"]


# ─────────────────────────── chunk ───────────────────────────


def test_chunk_splits_on_markdown_headings():
    chunks = chunk_markdown(WCAG, "standards/wcag.md")
    headings = [c.heading for c in chunks]
    assert "WCAG 2.2 — tiêu chí không áp dụng" in headings
    assert "Trường hợp không có nội dung áp dụng" in headings


def test_chunk_carries_a_file_line_anchor():
    chunks = chunk_markdown(WCAG, "standards/wcag.md")
    target = next(c for c in chunks if "đã thoả mãn" in c.text)
    assert target.doc_id == "standards/wcag.md"
    assert target.start_line >= 1
    assert target.end_line >= target.start_line
    assert target.citation.startswith("standards/wcag.md:")


def test_chunk_ids_are_unique():
    chunks = chunk_markdown(WCAG, "standards/wcag.md") + chunk_markdown(ISO, "standards/iso.md")
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


# ─────────────────────────── BM25 ───────────────────────────


def test_load_reads_every_markdown_under_kb(tmp_path):
    kb = KnowledgeBase.load(_kb(tmp_path))
    docs = {c.doc_id for c in kb.chunks}
    assert docs == {
        "standards/wcag.md",
        "standards/iso-25010.md",
        "house/testing-rules.md",
    }


def test_search_ranks_the_relevant_document_first(tmp_path):
    kb = KnowledgeBase.load(_kb(tmp_path))
    hits = kb.search("tiêu chí không có nội dung áp dụng vào thì tính thế nào", k=3)
    assert hits, "phải tìm được ít nhất một chunk"
    assert hits[0][0].doc_id == "standards/wcag.md"
    assert hits[0][1] > 0.0


def test_search_returns_empty_when_nothing_matches(tmp_path):
    kb = KnowledgeBase.load(_kb(tmp_path))
    assert kb.search("kubernetes helm chart rollout", k=5) == []


def test_search_is_deterministic_between_two_runs(tmp_path):
    kb = KnowledgeBase.load(_kb(tmp_path))
    query = "mẫu số coverage"
    first = [chunk.chunk_id for chunk, _ in kb.search(query, k=5)]
    second = [chunk.chunk_id for chunk, _ in kb.search(query, k=5)]
    assert first == second


# ─────────────────────────── build_context ───────────────────────────


def test_build_context_carries_citations(tmp_path):
    kb = KnowledgeBase.load(_kb(tmp_path))
    context = build_context("tiêu chí không có nội dung áp dụng", kb=kb, k=2)
    assert "[standards/wcag.md:" in context["text"]


def test_build_context_respects_the_configured_ceiling(tmp_path):
    kb = KnowledgeBase.load(_kb(tmp_path))
    cfg = Settings(context_max_chars=120)
    context = build_context("mẫu số coverage tiêu chí", kb=kb, k=6, settings=cfg)
    assert len(context["text"]) <= 120
    # Và phần bị bỏ phải ĐẾM ĐƯỢC, không được biến mất trong im lặng.
    assert isinstance(context["dropped_chunks"], list)


def test_build_context_returns_empty_string_when_kb_has_no_hit(tmp_path):
    kb = KnowledgeBase.load(_kb(tmp_path))
    assert build_context("kubernetes helm chart rollout", kb=kb) == ""


def test_build_context_on_an_empty_kb_directory(tmp_path):
    kb = KnowledgeBase.load(tmp_path / "trong-rong")
    assert len(kb) == 0
    assert build_context("bất kỳ câu hỏi nào", kb=kb) == ""
