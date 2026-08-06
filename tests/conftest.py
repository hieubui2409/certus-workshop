"""Đặt `src/backend` lên sys.path cho toàn bộ cây test.

Trùng ý với `pythonpath` trong `pytest.ini` — cố ý: ai chạy `pytest` từ một
rootdir khác (IDE, CI chạy trên thư mục con) sẽ không đọc `pytest.ini`, và
lúc đó lỗi hiện ra là `ModuleNotFoundError: app`, một thông báo không nói được
nguyên nhân thật.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
