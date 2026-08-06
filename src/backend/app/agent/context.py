"""Nạp prompt template và ghép nội dung người dùng upload vào prompt.

Đây là chỗ đường biên tin cậy của system-design §3.1 đi qua: mọi thứ đến từ file
upload — nội dung, tên file, comment, docstring, README, tên test, output khi
chạy test — đi vào cùng một cửa sổ ngữ cảnh với chỉ thị của hệ thống.

Placeholder dùng `{{TÊN}}` chứ không dùng `str.format`, vì prompt có rất nhiều
dấu ngoặc nhọn của JSON mẫu và `.format` sẽ diễn giải nhầm chúng.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

__all__ = [
    "PROMPTS_DIR",
    "load_prompt",
    "render_prompt",
    "render_template",
    "build_upload_context",
    "MissingPromptVariable",
]

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

#: File upload dài hơn ngần này bị rút gọn trước khi vào prompt, và phần bị bỏ
#: được nói ra bằng chữ ngay tại chỗ.
MAX_FILE_CHARS = 4000


class MissingPromptVariable(KeyError):
    """Template có placeholder mà caller không truyền giá trị.

    Không thay bằng chuỗi rỗng: một `{{NONCE}}` rỗng biến cơ chế chống trả lời
    lạc thành trang trí, và không có gì báo cho ai biết.
    """


def load_prompt(name: str) -> str:
    """Đọc `prompts/<name>.md`."""
    filename = name if name.endswith(".md") else f"{name}.md"
    path = PROMPTS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"không có prompt template: {path}")
    return path.read_text(encoding="utf-8")


def render_template(template: str, variables: Mapping[str, str]) -> str:
    """Thay mọi `{{TÊN}}`. Thiếu biến ⇒ nổ, nêu đích danh tên biến."""
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            missing.append(key)
            return match.group(0)
        return str(variables[key])

    rendered = _PLACEHOLDER.sub(replace, template)
    if missing:
        raise MissingPromptVariable(
            f"thiếu biến cho prompt: {', '.join(sorted(set(missing)))}"
        )
    return rendered


def render_prompt(name: str, **variables: str) -> str:
    return render_template(load_prompt(name), variables)


def _clip(source: str) -> str:
    if len(source) <= MAX_FILE_CHARS:
        return source
    remaining = len(source) - MAX_FILE_CHARS
    return source[:MAX_FILE_CHARS] + f"\n... (đã bỏ {remaining} ký tự cuối file)"


def build_upload_context(files: Mapping[str, str]) -> str:
    """Ghép nội dung các file người dùng upload thành một khối cho prompt.

    Thứ tự theo đường dẫn để hai lần phân tích cùng một repo sinh ra cùng một
    prompt — prompt nhảy thứ tự thì prompt cache trượt và trace không so được.
    """
    parts: list[str] = []
    for path in sorted(files):
        source = _clip(files[path])
        parts.append(f"### {path}\n{source}")
    return "\n\n".join(parts)
