"""Kiểm thử cổng thanh toán."""

import pytest

from payments.gateway import ChargeStatus, PaymentError


def test_thu_tien_thanh_cong(gateway):
    charge = gateway.charge(150_000)
    assert charge.status is ChargeStatus.SUCCEEDED
    assert charge.currency == "VND"
    assert charge.id.startswith("ch_")


def test_tu_choi_so_tien_khong_duong(gateway):
    with pytest.raises(PaymentError):
        gateway.charge(0)


def test_tu_choi_so_tien_vuot_tran(gateway):
    with pytest.raises(PaymentError):
        gateway.charge(20_000_000)


def test_idempotency_key_tra_ve_dung_giao_dich_cu(gateway):
    first = gateway.charge(100_000, idempotency_key="order-1")
    second = gateway.charge(100_000, idempotency_key="order-1")
    assert first.id == second.id


def test_lay_giao_dich_khong_ton_tai(gateway):
    with pytest.raises(PaymentError):
        gateway.get("ch_khong_co")


def test_hoan_tien_toan_phan(gateway):
    charge = gateway.charge(100_000)
    refunded = gateway.refund(charge.id)
    assert refunded.status is ChargeStatus.REFUNDED
    assert refunded.refundable == 0


def test_hoan_tien_mot_phan(gateway):
    charge = gateway.charge(100_000)
    partial = gateway.refund(charge.id, 40_000)
    assert partial.status is ChargeStatus.PARTIALLY_REFUNDED
    assert partial.refundable == 60_000


def test_khong_hoan_qua_so_tien_con_lai(gateway):
    charge = gateway.charge(100_000)
    gateway.refund(charge.id, 60_000)
    with pytest.raises(PaymentError):
        gateway.refund(charge.id, 60_000)


def test_khong_hoan_lai_giao_dich_da_hoan_het(gateway):
    charge = gateway.charge(100_000)
    gateway.refund(charge.id)
    with pytest.raises(PaymentError):
        gateway.refund(charge.id)


def test_chu_ky_webhook_dung(gateway):
    payload = b'{"type":"charge.succeeded"}'
    assert gateway.verify_webhook(payload, gateway.sign_webhook(payload)) is True


def test_chu_ky_webhook_sai(gateway):
    payload = b'{"type":"charge.succeeded"}'
    assert gateway.verify_webhook(payload, "0" * 64) is False


def test_metadata_duoc_giu(gateway):
    charge = gateway.charge(100_000, metadata={"order_id": "A-1"})
    assert charge.metadata == {"order_id": "A-1"}
