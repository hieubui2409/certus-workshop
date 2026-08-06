"""Token và scope.

Cái được khoá ở đây là CƠ CHẾ: token đi vòng tròn được, hết hạn thì bị từ chối,
chữ ký sai thì bị từ chối, thiếu scope thì `PermissionDenied` nêu đúng scope
thiếu. Bảng ai-có-scope-gì là CHÍNH SÁCH — nó phải sửa được mà không phải sửa
test, nếu không thì mỗi lần siết quyền lại phải đi sửa một tệp test để cho nó
hết đỏ, và đó đúng là cách một hàng rào biến thành thủ tục.
"""

from __future__ import annotations

import time

import pytest
import yaml

from app.auth import jwt_auth
from app.auth.jwt_auth import decode_token, issue_token, principal_from_header
from app.auth.scopes import (
    MACHINE_ONLY_SCOPES,
    ROLE_SCOPES,
    SCOPES,
    Principal,
    assert_scope,
    has_scope,
    require,
    scopes_for,
)
from app.contracts.errors import ConfigError, PermissionDenied
from app.settings import settings


@pytest.fixture()
def auth_cfg(tmp_path) -> str:
    path = tmp_path / "auth.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "issuer": "certus-test",
                "audience": "certus-ui",
                "token_ttl_seconds": 3600,
                "clock_skew_seconds": 0,
                "demo_accounts": {"u-viewer": "viewer", "u-admin": "admin"},
            }
        ),
        encoding="utf-8",
    )
    return str(path)


# ------------------------------------------------------------------ bảng scope


def test_moi_role_chi_dung_scope_co_that() -> None:
    for role, scopes in ROLE_SCOPES.items():
        unknown = set(scopes) - set(SCOPES)
        assert not unknown, f"vai {role} khai scope không tồn tại: {unknown}"


def test_admin_bao_ham_moi_vai_khac() -> None:
    admin = scopes_for("admin")
    for role in ROLE_SCOPES:
        assert scopes_for(role) <= admin, f"vai {role} có scope mà admin không có"


def test_scope_chi_danh_cho_may_khong_cap_cho_nguoi() -> None:
    """`grid:project` ghi band. Band là DERIVED — không có API surface nào nhận
    band từ ngoài, nên không vai người dùng nào được cầm scope này."""
    for role in ("viewer", "analyst"):
        assert not (scopes_for(role) & MACHINE_ONLY_SCOPES)


def test_vai_khong_ton_tai_thi_no_chu_khong_tra_ve_rong() -> None:
    # Fail-closed: một vai lạ KHÔNG được hiểu thành "vai không có quyền gì".
    with pytest.raises(ConfigError) as exc:
        scopes_for("super-analyst")
    assert exc.value.key == "ROLE_SCOPES"


def test_viewer_chi_doc() -> None:
    viewer = scopes_for("viewer")
    assert "probe:run" not in viewer
    assert "gate:override" not in viewer
    assert "ledger:append" not in viewer


# ------------------------------------------------------------------- require


def _principal(role: str, sub: str = "u1") -> Principal:
    return Principal(sub=sub, role=role, scopes=scopes_for(role))


def test_require_cho_qua_khi_du_scope() -> None:
    p = _principal("viewer")
    assert require("grid:read")(p) is p


def test_require_chan_khi_thieu_scope_va_neu_dich_danh() -> None:
    p = _principal("viewer")
    with pytest.raises(PermissionDenied) as exc:
        require("gate:override")(p)
    assert exc.value.needed == "gate:override"
    assert "u1" in str(exc.value)  # actor nằm trong thông báo, để soát được


def test_require_tu_choi_scope_khong_ton_tai() -> None:
    with pytest.raises(ConfigError):
        require("config:delete")(_principal("admin"))


def test_has_scope_va_assert_scope_dong_bo() -> None:
    p = _principal("analyst")
    for scope in SCOPES:
        if has_scope(p, scope):
            assert assert_scope(p, scope) is p
        else:
            with pytest.raises(PermissionDenied):
                assert_scope(p, scope)


# ---------------------------------------------------------------------- token


def test_token_di_vong_tron(auth_cfg: str) -> None:
    token = issue_token("u-admin", "admin", config_path=auth_cfg)
    principal = decode_token(token, config_path=auth_cfg)
    assert principal.sub == "u-admin"
    assert principal.role == "admin"
    assert principal.scopes == scopes_for("admin")


def test_token_het_han_bi_tu_choi(auth_cfg: str) -> None:
    token = issue_token("u-viewer", "viewer", ttl_seconds=-1, config_path=auth_cfg)
    with pytest.raises(PermissionDenied):
        decode_token(token, config_path=auth_cfg)


def test_token_ky_bang_khoa_khac_bi_tu_choi(auth_cfg: str, monkeypatch) -> None:
    token = issue_token("u-admin", "admin", config_path=auth_cfg)
    monkeypatch.setattr(settings, "jwt_secret", "một-khoá-hoàn-toàn-khác")
    with pytest.raises(PermissionDenied):
        decode_token(token, config_path=auth_cfg)


def test_token_sai_issuer_bi_tu_choi(tmp_path, auth_cfg: str) -> None:
    token = issue_token("u-admin", "admin", config_path=auth_cfg)
    other = tmp_path / "auth-other.yaml"
    cfg = yaml.safe_load(open(auth_cfg, encoding="utf-8"))
    cfg["issuer"] = "certus-mot-ban-build-khac"
    other.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(PermissionDenied):
        decode_token(token, config_path=str(other))


def test_scope_trong_token_khong_vuot_qua_bang_hien_thoi(auth_cfg: str) -> None:
    """Token tự khai thêm scope không có tác dụng: giao với bảng hiện thời."""
    import jwt as pyjwt

    cfg = yaml.safe_load(open(auth_cfg, encoding="utf-8"))
    forged = pyjwt.encode(
        {
            "sub": "u-viewer",
            "role": "viewer",
            "scopes": sorted(SCOPES),  # tự phong toàn quyền
            "iss": cfg["issuer"],
            "aud": cfg["audience"],
            "exp": int(time.time()) + 600,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    principal = decode_token(forged, config_path=auth_cfg)
    assert principal.scopes == scopes_for("viewer")


def test_token_thieu_exp_bi_tu_choi_khong_song_vinh_vien(auth_cfg: str) -> None:
    """Token đúc thiếu hẳn claim `exp` phải bị từ chối, không được sống mãi.

    PyJWT chỉ kiểm `exp` NẾU nó có mặt trong payload — thiếu `options={
    "require": [...]}`, một token thiếu `exp` qua được `decode_token` và
    không bao giờ hết hạn. Test này đúc token đó bằng tay (bỏ qua
    `issue_token`, vì `issue_token` luôn tự thêm `exp`) để chạm thẳng vào lỗ
    hổng ở `jwt.decode(...)`.
    """
    import jwt as pyjwt

    cfg = yaml.safe_load(open(auth_cfg, encoding="utf-8"))
    forged = pyjwt.encode(
        {
            "sub": "u-admin",
            "role": "admin",
            "scopes": sorted(SCOPES),
            "iss": cfg["issuer"],
            "aud": cfg["audience"],
            # cố ý KHÔNG có "exp"
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(PermissionDenied):
        decode_token(forged, config_path=auth_cfg)


def test_khong_co_header_thi_khong_co_principal_an_danh(auth_cfg: str) -> None:
    for header in (None, "", "Basic abc", "Bearer"):
        with pytest.raises(PermissionDenied):
            principal_from_header(header, config_path=auth_cfg)


def test_header_bearer_hop_le(auth_cfg: str) -> None:
    token = issue_token("u-viewer", "viewer", config_path=auth_cfg)
    p = principal_from_header(f"Bearer {token}", config_path=auth_cfg)
    assert p.role == "viewer"


# ---------------------------------------------------------------- config auth


def test_auth_config_thieu_khoa_thi_no_va_neu_dich_danh(tmp_path) -> None:
    path = tmp_path / "auth.yaml"
    path.write_text(yaml.safe_dump({"issuer": "x", "audience": "y"}), encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        jwt_auth.load_auth_config(path)
    assert exc.value.key in ("token_ttl_seconds", "clock_skew_seconds", "demo_accounts")


def test_auth_config_that_cua_du_an_nap_duoc() -> None:
    cfg = jwt_auth.load_auth_config(settings.config_dir / "auth.yaml")
    for key in jwt_auth.REQUIRED_KEYS:
        assert key in cfg
    # Mọi vai trong demo_accounts phải có mặt trong bảng scope, nếu không thì
    # lỗi chỉ lộ ra lúc có người đăng nhập bằng đúng tài khoản đó.
    for role in jwt_auth.demo_accounts(settings.config_dir / "auth.yaml").values():
        assert role in ROLE_SCOPES
