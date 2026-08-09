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


# Những trường của `Claim` mà mô hình hay nhét NHẦM vào trong `flags`. Đo được
# trên cassette thật: `"flags": [{"mechanism": "Đối chiếu số ô unknown = 8 …"}]`
# — nội dung đúng, chỗ để sai. Vớt các khoá này ra đúng chỗ của chúng.
_FLAG_HOISTABLE = ("mechanism",)


def _normalize_flags(item: Mapping[str, Any]) -> dict[str, Any]:
    """Chuẩn hoá `flags` về `list[str]`, và vớt lại thứ bị đặt nhầm chỗ.

    Hợp đồng nói `flags` là danh sách chuỗi, nhưng mô hình sinh ra ba dạng và
    cả ba đều mang thông tin người dùng CẦN đọc:

    · `"needs_kb:house/risk-bands.md"` — đúng khuôn, giữ nguyên.
    · `{"mechanism": "…"}` — trường top-level bị nhét vào nhầm; nâng nó lên
      thành `mechanism` thật để `ClaimInspector` in ra dòng "cơ chế: …",
      thay vì hiển thị một object rỗng nghĩa dưới dạng badge.
    · `{"na_reason": "legacy_exempt"}` — cờ viết dạng object; ép về đúng quy
      ước `khoá:giá trị` mà `flags` vốn đã dùng trong cả repo.

    Trả về một BẢN SAO của claim thô với `flags` đã sạch và các trường vớt
    được điền vào đúng chỗ — chỉ khi mô hình BỎ TRỐNG trường đó, vì dữ liệu
    đặt đúng chỗ luôn thắng dữ liệu đặt nhầm chỗ.

    Bỏ chúng đi thay vì chuẩn hoá là chọn im lặng: mất đúng câu giải thích vì
    sao claim được suy ra, mà người đọc không hề biết là mình đang thiếu.
    """
    raw = item.get("flags")
    if raw is None:
        raw = []
    elif not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raw = [raw]

    overrides: dict[str, Any] = {}
    flags: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            flags.append(entry)
            continue
        if isinstance(entry, Mapping):
            for key, value in entry.items():
                if key in _FLAG_HOISTABLE and not item.get(key) and isinstance(value, str):
                    overrides[key] = value
                else:
                    flags.append(f"{key}:{value}")
            continue
        # Không phải chuỗi, không phải object — vẫn hiện nguyên văn. FlagList
        # in cờ lạ ra thay vì lọc bỏ, và ở đây cũng vậy.
        flags.append(str(entry))

    return {**item, **overrides, "flags": flags}


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


def _label_from_evidence(item: Mapping[str, Any]) -> Label:
    """Suy nhãn từ BẰNG CHỨNG, không đọc trường `label` mô hình tự ghi.

    Đây là chỗ luật 'only a tool promotes a claim' được cưỡng chế. Mô hình
    vẫn được đề xuất nhãn — đề xuất đó chỉ không có hiệu lực.
    """
    has_anchor = bool(item.get("anchors"))
    has_evidence = bool(item.get("evidence_ids"))
    if has_anchor and has_evidence:
        return Label.OBSERVED
    if has_evidence:
        return Label.DERIVED
    if item.get("mechanism"):
        return Label.PRIOR
    return Label.ASSUMED


def parse_claims(raw: Mapping[str, Any]) -> list[Claim]:
    """Dựng danh sách `Claim` từ JSON model trả về."""
    items = raw.get("claims")
    if not isinstance(items, list):
        raise ClaimParseError("thiếu mảng 'claims' trong output của model")

    # Nắn khuôn những trường mô hình hay đặt sai chỗ, trước cả vòng kiểm khuôn.
    # Thứ không phải object thì để nguyên cho vòng dưới nêu đích danh chỗ hỏng.
    items = [_normalize_flags(c) if isinstance(c, Mapping) else c for c in items]

    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ClaimParseError(f"claim #{position} không phải object")
        _validate_shape(item, position)

    # Dựng bằng constructor thật, KHÔNG đi đường vòng bỏ qua validator — kể cả
    # validator đang canh đúng luật này trong contracts/types.py.
    #
    # Và nhãn KHÔNG lấy từ trường `label` mô hình tự ghi. Chỉ tool mới được
    # thăng hạng một claim — nói tự tin hơn không làm claim đúng hơn. Không
    # có neo bằng chứng thì nhãn cao nhất có thể là ASSUMED.
    return [
        Claim(
            id=c["id"],
            text=c["text"],
            label=_label_from_evidence(c),
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
