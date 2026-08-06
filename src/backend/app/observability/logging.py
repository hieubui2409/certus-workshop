"""Log có cấu trúc bằng loguru.

Hai sink, cố ý:
  * `sys.stdout` — đọc lúc chạy, trên máy sinh viên là thứ duy nhất nhìn thấy.
  * `var/logs/certus.log` — dòng lệnh cuộn mất, tệp thì không. Có rotation nên
    một lượt chạy dài không lấp đầy đĩa của người khác.

Không tự viết logger: loguru lo phần an toàn theo luồng, rotation, và
`contextualize()` — ba chỗ mà bản tự viết bằng `logging` chuẩn hay sai.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Any, Iterator

from loguru import logger

from app.settings import settings

#: Khuôn một dòng log. Giữ ở một chỗ để hai sink không trôi khỏi nhau.
LOG_FORMAT = "{time} | {level} | {name}:{line} | {message}"

#: Rotation/retention: đủ để soi lại cả buổi workshop, không đủ để lấp đĩa.
ROTATION = "10 MB"
RETENTION = 5

_configured = False

#: Id của các sink DO MODULE NÀY tạo. Giữ lại để lần dựng sau chỉ gỡ đúng
#: chúng. `logger.remove()` trần gỡ sạch mọi sink, kể cả sink do người gọi
#: thêm vào — một import muộn sẽ lặng lẽ vứt sink của họ đi.
_own_sinks: list[int] = []


def setup_logging(*, force: bool = False) -> None:
    """Dựng sink. Gọi nhiều lần vẫn an toàn — lần thứ hai trở đi là no-op trừ
    khi `force=True`, để một lần import muộn không nhân đôi mọi dòng log."""
    global _configured
    if _configured and not force:
        return

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    for sink_id in _own_sinks:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass
    _own_sinks.clear()

    _own_sinks.append(
        logger.add(sys.stdout, format=LOG_FORMAT, level=settings.log_level, enqueue=True)
    )
    _own_sinks.append(
        logger.add(
        settings.log_dir / "certus.log",
        format=LOG_FORMAT,
        level=settings.log_level,
        rotation=ROTATION,
        retention=RETENTION,
        encoding="utf-8",
        enqueue=True,
        )
    )
    _configured = True


def get_logger():
    """Logger dùng chung. Tự dựng sink ở lần gọi đầu để không module nào phải
    nhớ gọi `setup_logging()` trước."""
    setup_logging()
    return logger


@contextmanager
def trace_context(trace_id: str, **extra: Any) -> Iterator[None]:
    """Gắn `trace_id` (và bất kỳ khoá nào khác) vào `extra` của mọi dòng log
    phát ra bên trong khối này.

    Dùng `logger.contextualize` của loguru chứ không truyền tay: một tham số
    truyền tay sẽ bị quên ở đúng nhánh cần nhất.
    """
    setup_logging()
    with logger.contextualize(trace_id=trace_id, **extra):
        yield


def log_llm_call(prompt: str, response: str) -> None:
    """Ghi lại một lời gọi LLM.

    Tách thành hàm riêng vì đây là chỗ DUY NHẤT trong hệ có payload lớn mà nội
    dung do người ngoài kiểm soát — muốn đổi luật ghi payload thì chỉ phải sửa
    một chỗ.
    """
    setup_logging()
    logger.info(f"LLM call\nprompt={prompt}\nresponse={response}")


def log_event(level: str, message: str, **fields: Any) -> None:
    """Một sự kiện có cấu trúc. `fields` đi vào `extra` để sink nào muốn in ra
    thì in, sink nào không thì thôi."""
    setup_logging()
    logger.bind(**fields).log(level.upper(), message)
