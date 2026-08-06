"""Fail-closed khi đứng CERTUS_ENV=production mà vẫn dùng jwt_secret mặc định.

Lỗ cố ý đo được: `jwt_secret` mặc định là hằng số công khai
(`dev-only-change-me`), nằm ngay trong git. Bản build nào vẫn dùng nguyên nó mà
phục vụ request thật thì ai đọc được repo cũng tự phát được token `admin`.
Test ở đây khóa đúng hành vi: dev/test giữ nguyên default chạy được, production
giữ nguyên default thì phải nổ ngay lúc khởi động — không đợi tới khi có ai khai
thác được nó.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.contracts.errors import ConfigError  # noqa: E402
from app.settings import DEFAULT_JWT_SECRET, Settings  # noqa: E402


def test_default_dev_khong_no() -> None:
    """Không khai `env`/`CERTUS_ENV` ⇒ `development`, secret mặc định vẫn chạy được."""
    s = Settings(_env_file=None)
    assert s.env == "development"
    assert s.jwt_secret_is_default()


def test_production_voi_secret_mac_dinh_bi_chan() -> None:
    """`CERTUS_ENV=production` + secret mặc định ⇒ `ConfigError` ngay lúc khởi động."""
    with pytest.raises(ConfigError) as exc:
        Settings(_env_file=None, env="production")
    assert exc.value.key == "jwt_secret"


def test_production_voi_secret_that_thi_qua(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đổi `jwt_secret` sang giá trị thật thì production không bị chặn."""
    s = Settings(_env_file=None, env="production", jwt_secret="mot-khoa-that-du-dai")
    assert s.env == "production"
    assert not s.jwt_secret_is_default()


def test_production_khong_phan_biet_hoa_thuong() -> None:
    """`Production`/`PRODUCTION` cũng phải bị chặn như `production` — không ai nên
    thoát được kiểm tra này chỉ vì viết hoa khác."""
    with pytest.raises(ConfigError):
        Settings(_env_file=None, env="PRODUCTION")


def test_jwt_secret_is_default_dung_hang_so_cong_khai() -> None:
    """Hàm kiểm phải so sánh đúng với hằng số `DEFAULT_JWT_SECRET`, không phải
    một chuỗi hằng cứng đời ở nơi khác — hai nơi khắc hằng số này mà lệch nhau là đúng
    lớp lỗi test này tồn tại để chặn."""
    s = Settings(_env_file=None, jwt_secret=DEFAULT_JWT_SECRET)
    assert s.jwt_secret_is_default()
    s2 = Settings(_env_file=None, jwt_secret=DEFAULT_JWT_SECRET + "x")
    assert not s2.jwt_secret_is_default()
