"""Chính sách dữ liệu: lọc theo tên tệp, và che bí mật theo nội dung.

Test cố ý KHÔNG khoá cứng nội dung chính sách hiện hành (mẫu nào có trong danh
sách, dự án được phép sửa danh sách tới đâu). Chính sách sống trong
`config/data-policy.yaml` và trong bảng hằng số; khoá nó vào 40 dòng assert thì
lần nào có người sửa chính sách cho đúng, test cũng đỏ — và một test đỏ vì lý
do sai sẽ được người ta sửa cho hết đỏ.

Cái được khoá ở đây là CƠ CHẾ: danh sách ghép được, mẫu bí mật bắt đúng thứ,
config thiếu khoá thì nổ và nêu đích danh tên khoá.
"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from app.contracts.errors import ConfigError
from app.policy.data_policy import DataPolicy, PolicyDecision
from app.policy.redaction import (
    DEFAULT_BLOCKLIST,
    build_blocklist,
    find_secrets,
    redact_text,
)
from app.settings import settings

# --------------------------------------------------------------- blocklist


def test_blocklist_mac_dinh_khi_config_rong() -> None:
    assert build_blocklist({}) == DEFAULT_BLOCKLIST


def test_blocklist_extra_duoc_cong_them() -> None:
    patterns = build_blocklist({"blocklist_extra": ["id_rsa*", "*.p12"]})
    assert "id_rsa*" in patterns
    assert "*.p12" in patterns
    # Mẫu của dự án là phần THÊM, không thay chỗ của mẫu sẵn có.
    assert "*.pem" in patterns


def test_blocklist_khong_bao_gio_rong() -> None:
    """Một danh sách chặn rỗng đọc y hệt một danh sách chặn không tồn tại."""
    for cfg in ({}, {"blocklist_extra": []}, {"blocklist_override": ["*.pem"]}):
        assert build_blocklist(cfg), f"cfg={cfg} cho ra danh sách rỗng"


def test_default_blocklist_la_hang_so_code_khong_bi_doi_tai_cho() -> None:
    snapshot = list(DEFAULT_BLOCKLIST)
    build_blocklist({"blocklist_extra": ["*.xyz"]})
    assert DEFAULT_BLOCKLIST == snapshot


# ----------------------------------------------------------- mẫu bí mật


@pytest.mark.parametrize(
    "text, expected_pattern",
    [
        ("STRIPE_KEY=sk_live_51H8xQeAbCdEfGhIj", "stripe-live-key"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow==\n-----END RSA PRIVATE KEY-----", "private-key-block"),
        ("DB_PASSWORD=hunter2", "password-assignment"),
        ("password=hunter2", "password-assignment"),
        ("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE", "aws-access-key-id"),
        ("aws_secret_access_key=wJalrXUtnFEMI/K7MDENG", "aws-secret-access-key"),
        ("token = ghp_16CharactersAndMoreHere00", "github-token"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "bearer-token"),
    ],
)
def test_bat_duoc_bi_mat_theo_noi_dung(text: str, expected_pattern: str) -> None:
    hits = find_secrets(text)
    assert expected_pattern in {h.pattern for h in hits}


def test_van_ban_lanh_khong_bi_bao_nham() -> None:
    text = "def apply_discount(cart, coupon):\n    return cart.total * 0.9\n"
    assert find_secrets(text) == []
    assert redact_text(text).clean is True


def test_redact_thay_bang_nhan_mang_ten_mau() -> None:
    result = redact_text("STRIPE_KEY=sk_live_51H8xQeAbCdEfGhIj\n")
    assert "sk_live_51H8xQeAbCdEfGhIj" not in result.text
    assert "REDACTED" in result.text
    assert result.count >= 1
    # Nhãn phải nói được ĐÃ CHE CÁI GÌ — một dãy *** không phân biệt được
    # "có bí mật ở đây" với "chỗ này vốn trống".
    assert any(h.pattern in result.text for h in result.hits)


def test_bao_cao_ve_bi_mat_khong_chua_bi_mat() -> None:
    secret = "sk_live_51H8xQeAbCdEfGhIj"
    for hit in find_secrets(f"KEY={secret}"):
        assert secret not in hit.preview


def test_redact_nhieu_bi_mat_trong_mot_van_ban() -> None:
    text = "A=sk_live_AAAAAAAAAAAA\nB=sk_test_BBBBBBBBBBBB\npassword=zzz\n"
    result = redact_text(text)
    assert "sk_live_AAAAAAAAAAAA" not in result.text
    assert "sk_test_BBBBBBBBBBBB" not in result.text
    assert result.count >= 3


# --------------------------------------------------------------- data policy


def _write_cfg(tmp_path, **overrides) -> str:
    cfg = {
        "max_file_bytes": 1024,
        "binary_extensions": [".png", ".zip"],
        "blocklist_extra": ["id_rsa*"],
        "redact_placeholder": "[REDACTED:{name}]",
    }
    cfg.update(overrides)
    path = tmp_path / "data-policy.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return str(path)


def test_config_thieu_khoa_thi_no_va_neu_dich_danh(tmp_path) -> None:
    path = tmp_path / "data-policy.yaml"
    path.write_text(
        textwrap.dedent(
            """
            max_file_bytes: 1024
            binary_extensions: [".png"]
            blocklist_extra: []
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        DataPolicy.load(path)
    assert exc.value.key == "redact_placeholder"  # tên khoá, không phải "config sai"


def test_config_khong_ton_tai_thi_no(tmp_path) -> None:
    with pytest.raises(ConfigError):
        DataPolicy.load(tmp_path / "khong-co-tep-nay.yaml")


def test_allowlist_thieu_reason_thi_no(tmp_path) -> None:
    path = _write_cfg(tmp_path, allowlist_exact=[{"name": ".env.example"}])
    with pytest.raises(ConfigError) as exc:
        DataPolicy.load(path)
    assert "reason" in exc.value.key


def test_tep_khop_mau_chan_bi_loai_kem_ly_do(tmp_path) -> None:
    policy = DataPolicy.load(_write_cfg(tmp_path, blocklist_extra=["*.pem", "id_rsa*"]))
    decision = policy.decide("payments/server.pem")
    assert isinstance(decision, PolicyDecision)
    assert decision.allowed is False
    assert decision.matched_pattern == "*.pem"
    assert decision.reason  # lý do đọc được, không phải một cờ boolean trần


def test_allowlist_nguyen_van_thang_blocklist(tmp_path) -> None:
    path = _write_cfg(
        tmp_path,
        blocklist_extra=["*.env*"],
        allowlist_exact=[{"name": ".env.example", "reason": "khuôn mẫu, chỉ có giá trị giả"}],
    )
    policy = DataPolicy.load(path)
    assert policy.decide("payments/.env.example").allowed is True
    assert policy.decide("payments/.env").allowed is False


def test_tep_qua_lon_va_tep_nhi_phan_bi_loai(tmp_path) -> None:
    policy = DataPolicy.load(_write_cfg(tmp_path))
    assert policy.decide("src/big.py", size_bytes=999_999).allowed is False
    assert policy.decide("docs/logo.png").allowed is False
    assert policy.decide("src/cart.py", size_bytes=100).allowed is True


def test_select_tra_ve_ca_phan_bi_loai(tmp_path) -> None:
    """Danh sách bị loại LÀ mẫu số — không có nó thì không in được câu
    'đã loại N tệp vì lý do gì'."""
    policy = DataPolicy.load(_write_cfg(tmp_path, blocklist_extra=["*.pem"]))
    sent, decisions = policy.select(["src/cart.py", "certs/server.pem", "docs/logo.png"])
    assert sent == ["src/cart.py"]
    assert len(decisions) == 3
    assert sum(1 for d in decisions if not d.allowed) == 2


def test_preview_da_che_bi_mat(tmp_path) -> None:
    policy = DataPolicy.load(_write_cfg(tmp_path))
    out = policy.preview("STRIPE_SECRET_KEY=sk_live_51H8xQeAbCdEfGhIj\n")
    assert "sk_live_51H8xQeAbCdEfGhIj" not in out


def test_config_that_cua_du_an_nap_duoc() -> None:
    """Tệp đi kèm repo phải nạp được — một config chỉ đúng trong test là một
    config chưa từng chạy."""
    policy = DataPolicy.load(settings.config_dir / "data-policy.yaml")
    assert policy.max_file_bytes > 0
    assert policy.blocklist
    assert policy.binary_extensions
