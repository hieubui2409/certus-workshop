"""Phụ thuộc dùng chung cho các route.

Tồn tại vì một lý do cụ thể và đã đo được: `auth.jwt_auth.principal_from_header`
là một hàm thường nhận `authorization: str | None`. Cắm thẳng nó vào `Depends()`
thì FastAPI suy ra đó là **query param**, và request gửi đúng header `Authorization`
vẫn bị từ chối với thông báo `Field required · loc: ["query","authorization"]`.

Đó là loại lỗi tệ nhất trong nhóm này: kiểm quyền *trông như* đang chạy, mọi
request đều bị chặn nên không ai nghi ngờ, và cách sửa mà người vội hay chọn là
gỡ luôn `Depends` cho xong.
"""

from __future__ import annotations

from fastapi import Depends, Header

from app.auth.jwt_auth import principal_from_header
from app.auth.scopes import Principal


def current_principal(
    authorization: str | None = Header(default=None),
) -> Principal:
    """Rút principal từ header `Authorization: Bearer …`.

    Không có header ⇒ `PermissionDenied` (403), KHÔNG rơi về ẩn danh. Một
    principal ẩn danh im lặng biến mọi kiểm quyền phía sau thành trang trí.
    """
    return principal_from_header(authorization)


def needs(scope: str):
    """Dependency đòi một scope cụ thể.

    Tồn tại vì một phép đo: bảng scope khai **9 quyền, chỉ 2 được cưỡng chế**.
    Bảy quyền còn lại — `probe:run`, `repo:read`, `grid:read`, `gate:read`,
    `gate:override`, `grid:project`, `ledger:append` — không có một nơi gọi
    nào. Đo được: vai `viewer` (không có `probe:run`) gọi `POST /api/analyze`
    trả về **200**, tức chạy được `pytest` trong repo đích.

    Một bảng phân quyền đọc như đang bảo vệ mà thực ra không bảo vệ gì thì tệ
    hơn không có bảng: nó làm người đọc ngừng hỏi.
    """
    from app.auth.scopes import require

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        return require(scope)(principal)

    return dependency
