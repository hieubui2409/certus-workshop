"""Phát và kiểm token — PyJWT, thuật toán HS256.

GIỚI HẠN — phải nói thẳng vì nó dễ bị đọc nhầm thành một bảo đảm: HS256 là
khoá ĐỐI XỨNG. Ai xác minh được token thì KÝ được token. Cả backend và bất kỳ
thành phần nào cầm `settings.jwt_secret` đều tự phát được token `admin`. Cấu
hình này đủ cho một workshop chạy trên một máy, và **KHÔNG phải mẫu cho
production**. Bản production cần: khoá bất đối xứng (RS256/EdDSA) để khoá ký
tách hẳn khỏi khoá xác minh, có xoay khoá, có `jti` + danh sách thu hồi, và
`jwt_secret` không bao giờ nằm trong tệp settings có giá trị mặc định.

Không tự viết JWT: PyJWT lo phần base64url, phần `exp`/`nbf`/`aud`, và phần so
sánh chữ ký theo thời gian hằng — ba chỗ mà bản tự viết hay sai.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
import yaml
from jwt import InvalidTokenError

from app.auth.scopes import SCOPES, Principal, scopes_for
from app.contracts.errors import ConfigError, PermissionDenied
from app.settings import settings

#: Khoá bắt buộc của config/auth.yaml. Thiếu ⇒ ConfigError nêu đích danh.
REQUIRED_KEYS = ("issuer", "audience", "token_ttl_seconds", "clock_skew_seconds", "demo_accounts")

CONFIG_FILENAME = "auth.yaml"

_cache: dict[str, Any] | None = None


def load_auth_config(path: Path | str | None = None, *, reload: bool = False) -> dict[str, Any]:
    """Nạp `config/auth.yaml`, fail-closed.

    Cache lại vì nó được đọc ở mỗi request; `reload=True` cho test và cho lệnh
    nạp lại cấu hình.
    """
    global _cache
    if _cache is not None and not reload and path is None:
        return _cache

    cfg_path = Path(path) if path is not None else Path(settings.config_dir) / CONFIG_FILENAME
    if not cfg_path.exists():
        raise ConfigError(str(cfg_path), "tệp cấu hình auth không tồn tại")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(str(cfg_path), "nội dung không phải một mapping YAML")
    for key in REQUIRED_KEYS:
        if key not in raw:
            raise ConfigError(key, f"thiếu trong {cfg_path}")
    if path is None:
        _cache = raw
    return raw


def issue_token(
    sub: str,
    role: str,
    *,
    ttl_seconds: int | None = None,
    config_path: Path | str | None = None,
) -> str:
    """Phát token cho một chủ thể.

    Scope được giải NGAY TẠI ĐÂY từ role và đóng vào payload, để một token đã
    phát không đổi quyền khi bảng `ROLE_SCOPES` đổi giữa chừng — quyền của một
    phiên phải đọc được từ chính token đó, không phải từ trạng thái hiện thời
    của server.
    """
    cfg = load_auth_config(config_path)
    scopes = scopes_for(role)  # vai lạ nổ ở đây, không nổ lúc kiểm quyền
    ttl = ttl_seconds if ttl_seconds is not None else int(cfg["token_ttl_seconds"])
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "scopes": sorted(scopes),
        "iss": cfg["issuer"],
        "aud": cfg["audience"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, config_path: Path | str | None = None) -> Principal:
    """Kiểm chữ ký + hạn + issuer + audience, trả về `Principal`.

    Mọi lỗi của PyJWT được bọc thành `PermissionDenied`: biên ngoài không được
    thấy exception của thư viện, và thông báo lỗi không được tiết lộ token hỏng
    ở khâu nào.

    `algorithms` khai tường minh MỘT thuật toán — để ngỏ danh sách là cách mở
    cửa cho token ký bằng `alg: none`.

    `options={"require": [...]}` là bắt buộc, không phải trang trí: PyJWT chỉ
    kiểm một claim NẾU nó có mặt trong payload. Không có `require`, một token
    đúc thiếu hẳn `exp` được PyJWT coi là hợp lệ và sống vĩnh viễn — đã đo
    được bằng cách encode tay một token thiếu `exp` và thấy nó qua được decode
    trước bản vá này. `iss`/`aud` thực ra đã được PyJWT tự đòi có mặt khi
    truyền `issuer=`/`audience=` (đo bằng cùng cách), nhưng khai tường minh cả
    ba ở đây để không phụ thuộc vào hành vi ngầm định đó.
    """
    cfg = load_auth_config(config_path)
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=cfg["issuer"],
            audience=cfg["audience"],
            leeway=int(cfg["clock_skew_seconds"]),
            options={"require": ["exp", "iss", "aud"]},
        )
    except InvalidTokenError as exc:
        raise PermissionDenied("token hợp lệ", actor=None) from exc

    role = str(payload.get("role", ""))
    claimed = frozenset(payload.get("scopes") or [])
    # Giao với bảng hiện thời: token cũ không được mang một scope đã bị gỡ khỏi
    # vai của nó, và không được mang scope không tồn tại trong hệ.
    scopes = claimed & scopes_for(role) & SCOPES
    return Principal(
        sub=str(payload.get("sub", "")),
        role=role,
        scopes=scopes,
        exp=payload.get("exp"),
    )


def principal_from_header(
    authorization: str | None, *, config_path: Path | str | None = None
) -> Principal:
    """Rút token từ header `Authorization: Bearer …`.

    Không có header ⇒ `PermissionDenied`, KHÔNG rơi về một principal ẩn danh:
    một người dùng ẩn danh im lặng là cách mọi kiểm quyền phía sau trở thành
    trang trí.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PermissionDenied("Authorization: Bearer <token>")
    return decode_token(authorization.split(None, 1)[1].strip(), config_path=config_path)


def demo_accounts(config_path: Path | str | None = None) -> dict[str, str]:
    """Tài khoản demo của workshop: {username: role}. Chỉ để dựng phiên nhanh
    trên sân khấu, không phải cơ chế xác thực người dùng thật."""
    cfg = load_auth_config(config_path)
    accounts = cfg["demo_accounts"]
    if not isinstance(accounts, dict) or not accounts:
        raise ConfigError("demo_accounts", "cần mapping {username: role} khác rỗng")
    for role in accounts.values():
        scopes_for(str(role))  # vai lạ trong config nổ lúc nạp, không lúc đăng nhập
    return {str(k): str(v) for k, v in accounts.items()}
