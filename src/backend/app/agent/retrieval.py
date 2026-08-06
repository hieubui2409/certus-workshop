"""Nạp knowledge base, chunk theo heading, xếp hạng BM25, dựng context.

Vì sao chunk phải mang `file:line`: một câu trả lời không neo được vào chỗ nào
trong văn bản gốc thì người đọc không kiểm lại được, và citation chính là thứ
làm người đọc hạ cảnh giác. Neo sai còn nguy hiểm hơn không neo.

Vì sao BM25 tự viết: `requirements.txt` đã pin cứng vì ràng buộc "1000 sinh viên
pip install"; kéo thêm một gói xếp hạng cho 30 dòng công thức là đổi rủi ro cài
đặt lấy tiện lợi. Phần đáng dùng thư viện của sản phẩm nằm ở scipy/statsmodels
và allpairspy, không ở đây.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.settings import Settings, settings as default_settings

__all__ = ["Chunk", "KnowledgeBase", "build_context", "chunk_markdown", "tokenize"]

#: Section dài hơn ngần này bị chia tiếp tại ranh giới đoạn văn.
MAX_CHUNK_CHARS = 900

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_WORD = re.compile(r"\w+", re.UNICODE)

# BM25 Okapi. Hai hằng số này là giá trị chuẩn của công thức, không phải ngưỡng
# của phương pháp CERTUS — nên chúng ở đây chứ không ở config/*.yaml.
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """Hạ chữ thường, tách theo ký tự không phải chữ/số.

    `re.UNICODE` giữ nguyên tiếng Việt có dấu — tách theo [a-z0-9] sẽ băm
    "phủ" thành hai token vô nghĩa.
    """
    return [m.group(0).lower() for m in _WORD.finditer(text)]


@dataclass(frozen=True)
class Chunk:
    """Một đoạn của knowledge base, neo được vào file:line."""

    doc_id: str
    chunk_id: str
    heading: str
    text: str
    start_line: int
    end_line: int

    @property
    def citation(self) -> str:
        return f"{self.doc_id}:{self.start_line}-{self.end_line}"


def _split_long_section(
    doc_id: str, heading: str, lines: Sequence[str], first_line: int, index: int
) -> list[Chunk]:
    """Chia một section quá dài TẠI RANH GIỚI ĐOẠN VĂN, không cắt giữa dòng."""
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_start = first_line
    part = 0

    def flush(end_line: int) -> None:
        nonlocal buffer, buffer_start, part
        text = "\n".join(buffer).strip()
        if text:
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}#{index}.{part}",
                    heading=heading,
                    text=text,
                    start_line=buffer_start,
                    end_line=end_line,
                )
            )
            part += 1
        buffer = []

    for offset, line in enumerate(lines):
        line_no = first_line + offset
        buffer.append(line)
        too_long = sum(len(x) + 1 for x in buffer) >= MAX_CHUNK_CHARS
        if too_long and not line.strip():
            flush(line_no)
            buffer_start = line_no + 1
    flush(first_line + len(lines) - 1)
    return chunks


def chunk_markdown(text: str, doc_id: str) -> list[Chunk]:
    """Cắt theo ranh giới heading Markdown, giữ số dòng gốc."""
    lines = text.splitlines()
    sections: list[tuple[str, int, list[str]]] = []
    heading = doc_id
    start = 1
    body: list[str] = []

    for line_no, line in enumerate(lines, start=1):
        match = _HEADING.match(line)
        if match:
            if body:
                sections.append((heading, start, body))
            heading = match.group(2).strip()
            start = line_no
            body = [line]
        else:
            body.append(line)
    if body:
        sections.append((heading, start, body))

    chunks: list[Chunk] = []
    for index, (section_heading, section_start, section_lines) in enumerate(sections):
        raw = "\n".join(section_lines).strip()
        if not raw:
            continue
        if len(raw) <= MAX_CHUNK_CHARS:
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}#{index}",
                    heading=section_heading,
                    text=raw,
                    start_line=section_start,
                    end_line=section_start + len(section_lines) - 1,
                )
            )
        else:
            chunks.extend(
                _split_long_section(
                    doc_id, section_heading, section_lines, section_start, index
                )
            )
    return chunks


class KnowledgeBase:
    """Toàn bộ `kb/**/*.md` đã chunk, kèm chỉ mục BM25."""

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks: list[Chunk] = list(chunks)
        self._tokens: list[list[str]] = [tokenize(c.text) for c in self.chunks]
        self._lengths: list[int] = [len(t) for t in self._tokens]
        self._avg_len: float = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._freqs: list[Counter[str]] = [Counter(t) for t in self._tokens]
        document_freq: Counter[str] = Counter()
        for freq in self._freqs:
            document_freq.update(freq.keys())
        self._doc_freq = document_freq

    def __len__(self) -> int:
        return len(self.chunks)

    @classmethod
    def load(cls, kb_dir: Path | str | None = None, settings: Settings | None = None) -> "KnowledgeBase":
        cfg = settings or default_settings
        root = Path(kb_dir) if kb_dir is not None else Path(cfg.kb_dir)
        chunks: list[Chunk] = []
        if root.is_dir():
            for path in sorted(root.rglob("*.md")):
                doc_id = path.relative_to(root).as_posix()
                chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), doc_id))
        return cls(chunks)

    def _idf(self, term: str) -> float:
        n = len(self.chunks)
        df = self._doc_freq.get(term, 0)
        # Dạng có làm mượt của BM25: luôn dương, không sụp về 0 khi term có mặt
        # ở quá nửa số chunk.
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens: Sequence[str], index: int) -> float:
        freq = self._freqs[index]
        length = self._lengths[index] or 1
        total = 0.0
        for term in query_tokens:
            tf = freq.get(term, 0)
            if tf == 0:
                continue
            denom = tf + _K1 * (1 - _B + _B * length / (self._avg_len or 1.0))
            total += self._idf(term) * (tf * (_K1 + 1)) / denom
        return total

    def search(self, query: str, k: int = 6) -> list[tuple[Chunk, float]]:
        """Trả về k chunk khớp nhất, điểm giảm dần. Không khớp gì ⇒ danh sách rỗng."""
        query_tokens = tokenize(query)
        if not query_tokens or not self.chunks:
            return []
        scored = [
            (self.chunks[i], self.score(query_tokens, i)) for i in range(len(self.chunks))
        ]
        scored = [pair for pair in scored if pair[1] > 0.0]
        # Điểm bằng nhau thì xếp theo chunk_id để kết quả deterministic giữa hai
        # lượt chạy — một hàm retrieval nhảy thứ tự là một hàm không debug được.
        scored.sort(key=lambda pair: (-pair[1], pair[0].chunk_id))
        return scored[:k]


def _render(chunk: Chunk) -> str:
    """Một chunk trong context: dòng citation rồi tới nội dung."""
    return f"[{chunk.citation}] {chunk.heading}\n{chunk.text}"


def build_context(
    query: str,
    kb: KnowledgeBase | None = None,
    k: int = 6,
    settings: Settings | None = None,
) -> str:
    """Ghép các chunk khớp nhất thành khối context nhét vào prompt."""
    cfg = settings or default_settings
    knowledge = kb if kb is not None else KnowledgeBase.load(settings=cfg)
    hits = knowledge.search(query, k=k)
    if not hits:
        return ""
    chunks: Iterable[Chunk] = [chunk for chunk, _score in hits]
    combined = "\n\n".join(_render(c) for c in chunks)
    return combined[: cfg.context_max_chars]
