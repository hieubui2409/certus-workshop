"""Đọc cấu hình cổng thanh toán từ file .env.

Không dùng thư viện ngoài: file .env ở đây chỉ là `KEY=VALUE` mỗi dòng.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Tiền tố khoá bí mật của môi trường thật. Khoá `sk_test_` là khoá thử.
LIVE_KEY_PREFIX = "sk_live_"
TEST_KEY_PREFIX = "sk_test_"


class ConfigError(ValueError):
    """Cấu hình thiếu hoặc sai định dạng."""


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Đọc file .env thành dict. Bỏ qua dòng trống và dòng chú thích."""
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"dòng không hợp lệ trong {path}: {raw_line!r}")
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class GatewaySettings:
    """Cấu hình đã kiểm tra của cổng thanh toán."""

    secret_key: str
    webhook_secret: str
    currency: str = "VND"
    max_charge: int = 50_000_000

    @property
    def is_live(self) -> bool:
        return self.secret_key.startswith(LIVE_KEY_PREFIX)

    @property
    def masked_secret_key(self) -> str:
        """Dạng an toàn để đưa vào log: chỉ giữ tiền tố và 4 ký tự cuối."""
        if len(self.secret_key) <= 12:
            return "***"
        return f"{self.secret_key[:8]}…{self.secret_key[-4:]}"


REQUIRED_KEYS = ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")


def load_settings(env_path: str | Path) -> GatewaySettings:
    """Nạp cấu hình từ file .env và kiểm tra các khoá bắt buộc."""
    values = parse_env_file(env_path)
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise ConfigError(f"thiếu khoá cấu hình: {', '.join(missing)}")

    secret_key = values["STRIPE_SECRET_KEY"]
    if not secret_key.startswith((LIVE_KEY_PREFIX, TEST_KEY_PREFIX)):
        raise ConfigError("STRIPE_SECRET_KEY sai định dạng")

    return GatewaySettings(
        secret_key=secret_key,
        webhook_secret=values["STRIPE_WEBHOOK_SECRET"],
        currency=values.get("PAYMENTS_CURRENCY", "VND"),
        max_charge=int(values.get("PAYMENTS_MAX_CHARGE", 50_000_000)),
    )
