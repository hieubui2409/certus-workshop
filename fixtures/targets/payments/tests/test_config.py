"""Kiểm thử nạp cấu hình."""

import pytest

from payments.config import ConfigError, GatewaySettings, load_settings, parse_env_file


def test_doc_duoc_file_env_di_kem(env_path):
    values = parse_env_file(env_path)
    assert values["PAYMENTS_CURRENCY"] == "VND"


def test_bo_qua_dong_trong_va_chu_thich(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# chú thích\n\nA=1\n", encoding="utf-8")
    assert parse_env_file(path) == {"A": "1"}


def test_tu_choi_dong_khong_co_dau_bang(tmp_path):
    path = tmp_path / ".env"
    path.write_text("KHONG_CO_DAU_BANG\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        parse_env_file(path)


def test_load_settings_tu_file_di_kem(env_path):
    settings = load_settings(env_path)
    assert settings.currency == "VND"
    assert settings.max_charge == 50_000_000
    assert settings.is_live is True


def test_load_settings_bao_thieu_khoa(tmp_path):
    path = tmp_path / ".env"
    path.write_text("STRIPE_SECRET_KEY=sk_test_abc\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(path)


def test_load_settings_bao_sai_dinh_dang_khoa(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "STRIPE_SECRET_KEY=pk_live_abc\nSTRIPE_WEBHOOK_SECRET=whsec_x\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_settings(path)


def test_khoa_thu_khong_bi_coi_la_khoa_that(settings):
    assert settings.is_live is False


def test_mask_khoa_bi_mat():
    long_key = GatewaySettings(secret_key="sk_live_" + "x" * 20, webhook_secret="w")
    assert long_key.masked_secret_key == "sk_live_…xxxx"
    short_key = GatewaySettings(secret_key="sk_live_", webhook_secret="w")
    assert short_key.masked_secret_key == "***"
