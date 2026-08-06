"""Parse claim từ output của LLM thành `contracts.Claim`.

Mọi câu CERTUS nói về code của bạn đều là một `Claim` (system-design §5.1), nên
đây là cửa hẹp mà văn bản tự do của model phải đi qua để trở thành dữ liệu có
cấu trúc.

`Label`, `Anchor`, `Interval` import từ `app.contracts.types` — module này không
khai lại enum nào, vì một enum khai hai nơi là cách kinh điển để hai nửa hệ
thống trôi khỏi nhau mà không ai thấy.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.contracts.types import Anchor, Claim, Interval, Label

__all__ = ["extract_claims_json", "parse_claims", "ClaimParseError"]

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ClaimParseError(ValueError):
    """Output của model không đúng khuôn. Nêu đích danh chỗ hỏng."""


def _first_json_object(text: str) -> str | None:
    """Quét cân bằng ngoặc để lấy object JSON đầu tiên nằm trong văn bản."""
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : index + 1]
    return None


def extract_claims_json(text: str) -> dict[str, Any]:
    """Moi khối JSON ra khỏi câu trả lời.

    Prompt yêu cầu trả JSON và không gì khác, nhưng model vẫn thỉnh thoảng bọc
    trong code fence hoặc kèm một câu dẫn. Chấp nhận cả ba dạng ở đây là rẻ hơn
    nhiều so với để cả pipeline hỏng vì một dấu backtick.
    """
    fenced = _JSON_FENCE.search(text)
    candidate = fenced.group(1) if fenced else _first_json_object(text)
    if candidate is None:
        raise ClaimParseError("không tìm thấy object JSON nào trong output của model")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ClaimParseError(f"JSON hỏng: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ClaimParseError(f"mong đợi một object, nhận {type(parsed).__name__}")
    return parsed


def _anchors(raw: Sequence[Mapping[str, Any]] | None) -> list[Anchor]:
    return [Anchor(**dict(item)) for item in (raw or [])]


def _interval(raw: Mapping[str, Any] | None) -> Interval | None:
    return Interval(**dict(raw)) if raw else None


def _validate_shape(item: Mapping[str, Any], position: int) -> None:
    """Kiểm khuôn của một claim thô trước khi dựng model.

    `label` phải là một trong bốn giá trị của `Label`; sai enum thì dừng ngay và
    nói rõ nhận được gì, thay vì để pydantic báo một lỗi khó lần ngược.
    """
    for required in ("id", "text", "label"):
        if required not in item:
            raise ClaimParseError(f"claim #{position} thiếu trường {required!r}")
    try:
        Label(item["label"])
    except ValueError as exc:
        raise ClaimParseError(
            f"claim {item['id']!r}: nhãn {item['label']!r} không thuộc hệ 4 nhãn "
            f"({', '.join(label.value for label in Label)})"
        ) from exc


def parse_claims(raw: Mapping[str, Any]) -> list[Claim]:
    """Dựng danh sách `Claim` từ JSON model trả về."""
    items = raw.get("claims")
    if not isinstance(items, list):
        raise ClaimParseError("thiếu mảng 'claims' trong output của model")

    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ClaimParseError(f"claim #{position} không phải object")
        _validate_shape(item, position)

    # Khuôn đã kiểm ở trên rồi nên dựng thẳng bằng model_construct: chạy lại
    # validator của pydantic ở đây chỉ tốn thời gian cho mỗi claim mà không
    # thêm thông tin gì.
    return [
        Claim.model_construct(
            id=c["id"],
            text=c["text"],
            label=Label(c["label"]),
            k=c.get("k"),
            n=c.get("n"),
            interval=_interval(c.get("interval")),
            evidence_ids=list(c.get("evidence_ids") or []),
            anchors=_anchors(c.get("anchors")),
            flags=list(c.get("flags") or []),
            is_rate=bool(c.get("is_rate", False)),
            mechanism=c.get("mechanism"),
        )
        for c in items
    ]
