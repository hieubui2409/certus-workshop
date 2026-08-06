"""Kiểm thử phụ phí và ràng buộc thanh toán."""

import pytest

from shopcart.enums import PaymentMethod, ShippingZone
from shopcart.payment import (
    UnsupportedPaymentError,
    is_supported,
    payment_fee,
    validate_payment,
)


def test_cod_chi_phuc_vu_noi_dia():
    assert is_supported(PaymentMethod.COD, ShippingZone.DOMESTIC) is True
    assert is_supported(PaymentMethod.COD, ShippingZone.INTERNATIONAL) is False


def test_the_va_vi_phuc_vu_moi_tuyen():
    assert is_supported(PaymentMethod.CARD, ShippingZone.INTERNATIONAL) is True
    assert is_supported(PaymentMethod.WALLET, ShippingZone.REGIONAL) is True


def test_validate_tu_choi_cod_ngoai_noi_dia():
    with pytest.raises(UnsupportedPaymentError):
        validate_payment(PaymentMethod.COD, ShippingZone.REGIONAL, 100_000)


def test_validate_tu_choi_cod_vuot_tran():
    with pytest.raises(UnsupportedPaymentError):
        validate_payment(PaymentMethod.COD, ShippingZone.DOMESTIC, 9_000_000)


def test_validate_chap_nhan_don_hop_le():
    assert validate_payment(PaymentMethod.CARD, ShippingZone.DOMESTIC, 100_000) is None


@pytest.mark.parametrize(
    "method,expected",
    [
        (PaymentMethod.CARD, 1_500),
        (PaymentMethod.WALLET, 0),
        (PaymentMethod.COD, 2_000),
    ],
)
def test_phu_phi_theo_tung_phuong_thuc(method, expected):
    assert payment_fee(method, 100_000) == expected


def test_phu_phi_bi_ap_tran():
    assert payment_fee(PaymentMethod.CARD, 100_000_000) == 50_000
