"""Cổng thanh toán — bản chạy trong bộ nhớ, không gọi mạng.

Đủ thật để có cái mà đo: có idempotency key, có hoàn tiền một phần, có xác
thực chữ ký webhook bằng HMAC-SHA256.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass, field
from enum import Enum

from .config import GatewaySettings


class ChargeStatus(Enum):
    """Trạng thái một giao dịch thu tiền."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class GatewayRoute(Enum):
    """Đường đi của một giao dịch.

    Vài merchant chưa chuyển sang API mới nên vẫn đi qua cổng cũ. Hai đường có
    biểu phí khác nhau và trần khác nhau, nên chúng là hai vùng rủi ro khác
    nhau chứ không phải một chi tiết cài đặt.
    """

    MODERN = "modern"
    LEGACY = "legacy"


class PaymentError(ValueError):
    """Giao dịch bị từ chối."""


@dataclass
class Charge:
    """Một lần thu tiền."""

    id: str
    amount: int
    currency: str
    status: ChargeStatus = ChargeStatus.PENDING
    refunded: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def refundable(self) -> int:
        return self.amount - self.refunded


class PaymentGateway:
    """Cổng thanh toán trong bộ nhớ."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings
        self._charges: dict[str, Charge] = {}
        self._by_idempotency_key: dict[str, str] = {}

    def charge(
        self,
        amount: int,
        currency: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Charge:
        """Thu tiền. Cùng một `idempotency_key` luôn trả về đúng giao dịch cũ."""
        if idempotency_key and idempotency_key in self._by_idempotency_key:
            return self._charges[self._by_idempotency_key[idempotency_key]]

        if amount <= 0:
            raise PaymentError("số tiền phải > 0")
        if amount > self._settings.max_charge:
            raise PaymentError(
                f"vượt trần {self._settings.max_charge} của cổng thanh toán"
            )

        charge = Charge(
            id=f"ch_{uuid.uuid4().hex[:16]}",
            amount=amount,
            currency=currency or self._settings.currency,
            status=ChargeStatus.SUCCEEDED,
            metadata=dict(metadata or {}),
        )
        self._charges[charge.id] = charge
        if idempotency_key:
            self._by_idempotency_key[idempotency_key] = charge.id
        return charge

    def get(self, charge_id: str) -> Charge:
        if charge_id not in self._charges:
            raise PaymentError(f"không có giao dịch {charge_id}")
        return self._charges[charge_id]

    def refund(self, charge_id: str, amount: int | None = None) -> Charge:
        """Hoàn tiền toàn phần (mặc định) hoặc một phần."""
        charge = self.get(charge_id)
        if charge.status is ChargeStatus.REFUNDED:
            raise PaymentError("giao dịch đã hoàn tiền toàn phần")

        refund_amount = charge.refundable if amount is None else amount
        if refund_amount <= 0 or refund_amount > charge.refundable:
            raise PaymentError(
                f"số tiền hoàn phải trong khoảng 1..{charge.refundable}"
            )

        charge.refunded += refund_amount
        if charge.refunded == charge.amount:
            charge.status = ChargeStatus.REFUNDED
        else:
            charge.status = ChargeStatus.PARTIALLY_REFUNDED
        return charge

    def sign_webhook(self, payload: bytes) -> str:
        """Chữ ký mà cổng thật sẽ gửi kèm webhook."""
        return hmac.new(
            self._settings.webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """So sánh chữ ký theo thời gian hằng."""
        return hmac.compare_digest(self.sign_webhook(payload), signature)
