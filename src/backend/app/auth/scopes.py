"""Scope của agent và người dùng — ai được làm gì.

Bảng scope lấy từ `system-design.md` §7. Đây là chỗ ở DUY NHẤT của bảng đó;
route và agent tra ở đây chứ không tự khai lại tập scope của mình.

Nguyên tắc: `Principal` sống ở module này chứ không ở `jwt_auth.py`, để đồ thị
import chỉ có một chiều `jwt_auth → scopes`. Một vòng import giữa "ai là ai" và
"ai được làm gì" là cách nhanh nhất để hai bảng trôi khỏi nhau.
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from app.contracts.errors import ConfigError, PermissionDenied

#: Toàn bộ scope tồn tại trong hệ. Một scope không có tên ở đây là lỗi chính
#: tả, không phải một quyền mới — `assert_scope` từ chối nó.
SCOPES = frozenset(
    {
        "repo:read",  # đọc file đã upload
        "probe:run",  # chạy test trong sandbox
        "grid:read",  # đọc grid
        "grid:project",  # ghi band — band là DERIVED, chỉ orchestrator có
        "gate:read",  # đọc verdict
        "gate:override",  # ghi đè verdict, phải kèm reason
        "config:read",  # đọc config/*.yaml
        "config:write",  # sửa config/*.yaml
        "ledger:append",  # ghi evidence
    }
)

#: Vai → tập scope.
#: viewer  : chỉ đọc, dùng cho màn hình chiếu và người xem kết quả.
#: analyst : người đang phân tích một repo — chạy probe, đọc và chỉnh cấu hình
#:           phân tích của phiên làm việc của mình.
#: admin   : người vận hành CERTUS.
ROLE_SCOPES: dict[str, set[str]] = {
    "viewer": {"repo:read", "grid:read", "gate:read"},
    # 'config:write' ĐÃ GỠ khỏi analyst. Analyst là bên đang BỊ CHẤM; cho họ
    # sửa zones.yaml là cho họ hạ blocking_w, làm rỗng tập chặn, và mọi gate
    # xanh mà không dòng log nào nói ngưỡng vừa đổi.
    "analyst": {
        "repo:read",
        "grid:read",
        "gate:read",
        "probe:run",
        "config:read",
    },
    "admin": set(SCOPES),
}

#: Scope không bao giờ cấp cho người: chỉ orchestrator tự cấp cho mình khi chạy
#: bước 6. Band là DERIVED — không có API surface nào nhận band từ ngoài.
MACHINE_ONLY_SCOPES = frozenset({"grid:project"})


class Principal(BaseModel):
    """Chủ thể của một lời gọi. `scopes` đã giải xong từ role tại lúc phát
    token, để mỗi request không phải tra lại bảng."""

    sub: str
    role: str
    scopes: frozenset[str] = Field(default_factory=frozenset)
    exp: int | None = None

    def __str__(self) -> str:  # dùng trong thông báo lỗi và log
        return f"{self.sub}({self.role})"


def scopes_for(role: str) -> frozenset[str]:
    """Vai lạ ⇒ `ConfigError` nêu đích danh. Fail-closed: một vai không có
    trong bảng KHÔNG được hiểu thành "vai không có quyền gì" — nó là dấu hiệu
    token đến từ một bản build khác, và bản build đó có thể hiểu vai đó là admin.
    """
    if role not in ROLE_SCOPES:
        raise ConfigError("ROLE_SCOPES", f"vai {role!r} chưa được định nghĩa")
    return frozenset(ROLE_SCOPES[role])


def has_scope(principal: Principal, scope: str) -> bool:
    return scope in principal.scopes


def assert_scope(principal: Principal, scope: str) -> Principal:
    """Kiểm một scope. Thiếu ⇒ `PermissionDenied` nêu rõ thiếu scope nào."""
    if scope not in SCOPES:
        raise ConfigError("SCOPES", f"scope {scope!r} không tồn tại trong bảng")
    if not has_scope(principal, scope):
        raise PermissionDenied(scope, actor=str(principal))
    return principal


def require(scope: str) -> Callable[[Principal], Principal]:
    """Dựng một dependency kiểm scope, dùng được với `Depends(...)`.

    Module này ở tầng 2 nên KHÔNG import FastAPI: nó trả về một callable thuần
    nhận `Principal`, tầng 5 tự nối vào cơ chế dependency của nó.
    """

    def _dependency(principal: Principal) -> Principal:
        return assert_scope(principal, scope)

    _dependency.__name__ = f"require_{scope.replace(':', '_')}"
    _dependency.__doc__ = f"Yêu cầu scope {scope!r}."
    return _dependency
