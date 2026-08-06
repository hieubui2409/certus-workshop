"""Lỗi dùng chung. Toàn bộ đều fail-closed.

Nguyên tắc: gặp cấu hình thiếu hoặc hỏng thì DỪNG và nêu đích danh tên khoá,
tuyệt đối không âm thầm rơi về một giá trị mặc định. "Không có gì để soi là
MỘT SỰ CỐ CẤU HÌNH, không phải một kết quả tốt."
"""

from __future__ import annotations


class CertusError(Exception):
    """Gốc của mọi lỗi CERTUS."""


class ConfigError(CertusError):
    """Khoá cấu hình thiếu hoặc sai khuôn. Luôn nêu đích danh tên khoá."""

    def __init__(self, key: str, detail: str = "") -> None:
        self.key = key
        super().__init__(f"cấu hình hỏng ở khoá {key!r}" + (f": {detail}" if detail else ""))


class NAConflictError(CertusError):
    """Cell khai N/A mà lại có executed record.

    Tính toàn vẹn của mẫu số là toàn bộ lý do module grid tồn tại — một ô vừa
    "không áp dụng được" vừa "đã chạy thật" thì một trong hai là sai.
    """


class ZoneWeightConflictError(CertusError):
    """Hai cell cùng zone khai weight khác nhau.

    KHÔNG average, KHÔNG max, KHÔNG first-wins: đã đo được ca một cell mang
    w=0.9 nằm trong zone báo w=0.1, khiến cả zone tụt dưới ngưỡng chặn và
    thoát khỏi release block.
    """


class ZoneWithoutScoreableCellsError(CertusError):
    """Zone không còn cell nào chấm được.

    Nếu trả kết quả thiếu thay vì nổ, zone đó BIẾN MẤT khỏi min_per_zone trong
    im lặng — đã đo được ca một N/A duy nhất trên zone nặng nhất (w=0.95) làm
    cả zone rời khỏi con số vốn LÀ cái gate, và lượt chạy báo PASS.
    """


class EmptyDenominatorError(CertusError):
    """N == 0. Mẫu số rỗng là ĐỎ, không phải xanh.

    "Đã soi 40 thứ, thấy 0 lỗi" khác hoàn toàn "0 lỗi" trơ trọi — cái sau
    không phân biệt được với "chưa soi cái nào".
    """


class DegenerateMarginalError(CertusError):
    """rho có mẫu số ~0. Thà nổ còn hơn trả một con số vô nghĩa."""


class CassetteMissError(CertusError):
    """LLM_MODE=mock nhưng không có bản ghi khớp.

    Tuyệt đối không được trả rỗng: một cassette miss im lặng đọc y hệt một
    lời gọi LLM trả về rỗng, và hai thứ đó cần hai cách xử lý khác nhau.
    """


class UnverifiableClaimError(CertusError):
    """Claim không có neo. Downstream coi như không tồn tại."""


class SandboxViolation(CertusError):
    """Lệnh bị chặn bởi sandbox. Ghi lại đầy đủ argv để soát được."""

    def __init__(self, argv: list[str], reason: str) -> None:
        self.argv = argv
        self.reason = reason
        super().__init__(f"lệnh bị chặn ({reason}): {' '.join(argv)}")


class PermissionDenied(CertusError):
    """Thiếu scope. Nêu rõ scope nào thiếu."""

    def __init__(self, needed: str, actor: str | None = None) -> None:
        self.needed = needed
        self.actor = actor
        super().__init__(f"thiếu scope {needed!r}" + (f" (actor={actor})" if actor else ""))


class EmptyBlockingSetError(CertusError):
    """Sau khi compile zones, không rule nào chạm blocking_w.

    Bên bị chấm không được phép làm rỗng tập chặn — tập chặn rỗng là lỗi cấu
    hình, không phải một kết quả tốt.
    """
