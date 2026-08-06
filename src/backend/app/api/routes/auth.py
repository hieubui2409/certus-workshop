"""Phát token cho tài khoản demo của workshop.

Nói thẳng ở đây thay vì để người đọc tự phát hiện: đây **không phải** cơ chế
xác thực người dùng thật. Không có mật khẩu, không có thư mục người dùng — chỉ
có ba tài khoản khai sẵn trong `config/auth.yaml` để dựng phiên nhanh trên sân
khấu và để phần phân quyền có thứ để phân.

Điều nó vẫn làm đúng, và cần đúng: token mang `role` đã giải thành `scopes` tại
lúc phát, nên mọi kiểm quyền phía sau là kiểm THẬT. Đường tắt nằm ở chỗ *ai là
ai*, không nằm ở chỗ *ai được làm gì*.
"""

from __future__ import annotations

from fastapi import APIRouter, Body

from app.auth.jwt_auth import demo_accounts, issue_token
from app.contracts.errors import PermissionDenied

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/accounts")
def accounts() -> dict:
    """Liệt kê tài khoản demo và role của chúng.

    Công khai có chủ đích: giấu danh sách này không thêm chút an toàn nào (token
    ký bằng HS256 với khoá trong config), mà chỉ làm sinh viên mất 20 phút đoán
    tên tài khoản.
    """
    return {"accounts": demo_accounts(), "note": "tài khoản demo, không có mật khẩu"}


@router.post("/login")
def login(username: str = Body(..., embed=True)) -> dict:
    table = demo_accounts()
    if username not in table:
        raise PermissionDenied(
            f"không có tài khoản demo {username!r}. Có: {sorted(table)}"
        )
    role = table[username]
    return {"token": issue_token(username, role), "role": role, "sub": username}
