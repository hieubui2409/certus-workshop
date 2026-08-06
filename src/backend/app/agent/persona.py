"""Cá nhân hoá: nhớ thói quen kiểm thử của từng người và bài học của từng project.

Hai loại ký ức khác nhau về bản chất:

- **thói quen** thuộc về NGƯỜI ("bạn hay quên test nhánh lỗi") — mang theo giữa
  các project là đúng ý đồ;
- **bài học** thuộc về PROJECT ("hàm apply_discount thiếu test cho coupon hết
  hạn") — nó chứa định danh cụ thể của một mã nguồn cụ thể.

Lưu trong SQLite ở `settings.db_path`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.settings import Settings, settings as default_settings

__all__ = ["PersonaStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    habit       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    project_id  TEXT,
    lesson      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_habits_user  ON habits(user_id);
CREATE INDEX IF NOT EXISTS idx_lessons_user ON lessons(user_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersonaStore:
    """Kho ký ức của CERTUS về người dùng."""

    def __init__(
        self, db_path: Path | str | None = None, settings: Settings | None = None
    ) -> None:
        cfg = settings or default_settings
        path = Path(db_path) if db_path is not None else Path(cfg.db_path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "PersonaStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- thói quen: thuộc về người ---------------------------------------

    def record_habit(self, user_id: str, habit: str) -> None:
        """Ghi một thói quen kiểm thử quan sát được ở người dùng này."""
        self.db.execute(
            "INSERT INTO habits (user_id, habit, created_at) VALUES (?, ?, ?)",
            (user_id, habit, _now()),
        )
        self.db.commit()

    def habits_for(self, user_id: str, limit: int = 10) -> list[str]:
        rows = self.db.execute(
            "SELECT habit FROM habits WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [row["habit"] for row in rows]

    # --- bài học ----------------------------------------------------------

    def record_lesson(self, user_id: str, project_id: str, lesson: str) -> None:
        """Ghi một bài học rút ra được trong lúc phân tích."""
        self.db.execute(
            "INSERT INTO lessons (user_id, lesson, created_at) VALUES (?, ?, ?)",
            (user_id, lesson, _now()),
        )
        self.db.commit()

    def lessons_for(self, user_id: str, limit: int = 10) -> list[str]:
        """Trả về bài học đã rút ra cho người dùng này."""
        rows = self.db.execute(
            "SELECT lesson FROM lessons WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [row["lesson"] for row in rows]

    # --- khối chữ cho prompt ---------------------------------------------

    def persona_block(self, user_id: str) -> str:
        """Dựng khối chữ nhét vào prompt. Không có gì để nói ⇒ chuỗi rỗng.

        Trả rỗng thay vì một câu kiểu "chưa có dữ liệu cá nhân hoá" là có chủ ý:
        một dòng nói về sự vắng mặt của dữ liệu vẫn là một dòng model sẽ diễn
        giải, và nó thường diễn giải thành lời xin lỗi trong câu trả lời.
        """
        habits = self.habits_for(user_id)
        lessons = self.lessons_for(user_id)
        if not habits and not lessons:
            return ""
        lines: list[str] = []
        if habits:
            lines.append("Thói quen kiểm thử đã quan sát được ở người dùng này:")
            lines.extend(f"- {habit}" for habit in habits)
        if lessons:
            if lines:
                lines.append("")
            lines.append("Bài học từ các lần phân tích trước:")
            lines.extend(f"- {lesson}" for lesson in lessons)
        return "\n".join(lines)
