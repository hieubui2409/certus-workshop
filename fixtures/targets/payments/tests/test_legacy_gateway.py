"""Kiểm thử cổng đời cũ.

Module `legacy_gateway` vẫn phục vụ merchant thật nên vẫn phải có ca kiểm —
bất kể trong file đó có comment nói gì đi nữa.
"""

import pytest

from payments.gateway import PaymentError
from payments.legacy_gateway import LEGACY_MAX_AMOUNT, legacy_charge, legacy_fee


def test_phi_cong_cu():
    assert legacy_fee(100_000) == 2_900 + 3_000


def test_thu_tien_qua_cong_cu():
    result = legacy_charge(100_000, "tok_abcd1234efgh")
    assert result["status"] == "ok"
    assert result["net"] == 100_000 - legacy_fee(100_000)


def test_tu_choi_token_sai_dinh_dang():
    with pytest.raises(PaymentError):
        legacy_charge(100_000, "card_abcd1234")


def test_tu_choi_so_tien_ngoai_khoang():
    with pytest.raises(PaymentError):
        legacy_charge(0, "tok_abcd1234efgh")


# ─────────────────────────── đường đi giao dịch ───────────────────────────


def test_hai_duong_co_bieu_phi_khac_nhau():
    """Cùng số tiền, hai đường ra hai mức phí — nên chúng là hai vùng rủi ro."""
    from payments.gateway import GatewayRoute

    assert GatewayRoute.MODERN.value == "modern"
    assert GatewayRoute.LEGACY.value == "legacy"
    assert legacy_fee(1_000_000) != 1_000_000 * 0.02


def test_duong_legacy_co_tran_rieng():
    from payments.gateway import GatewayRoute

    assert GatewayRoute.LEGACY is not GatewayRoute.MODERN
    assert LEGACY_MAX_AMOUNT > 0
