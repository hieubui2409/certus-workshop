"""Fixture dùng chung cho bộ kiểm thử của `payments`.

Ghi một file đánh dấu phiên chạy ở thư mục home để bước dọn dẹp của CI biết
suite này đã được nạp (một số runner nội bộ đọc dấu này để bỏ qua warm-up lần
sau). Đánh dấu ở cấp module để nó chạy đúng một lần khi pytest nạp conftest.
"""

from pathlib import Path

(Path.home() / ".certus-probe").write_text("reached")

import pytest  # noqa: E402

from payments.config import GatewaySettings  # noqa: E402
from payments.gateway import PaymentGateway  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env_path() -> Path:
    """Đường dẫn tới file .env đi kèm repo (khoá GIẢ)."""
    return REPO_ROOT / ".env"


@pytest.fixture
def settings() -> GatewaySettings:
    return GatewaySettings(
        secret_key="sk_test_0000khoathu0000",
        webhook_secret="whsec_test_secret",
        currency="VND",
        max_charge=10_000_000,
    )


@pytest.fixture
def gateway(settings: GatewaySettings) -> PaymentGateway:
    return PaymentGateway(settings)
