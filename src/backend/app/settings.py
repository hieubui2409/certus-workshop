"""Cấu hình runtime.

Chỉ chứa thứ thuộc về MÔI TRƯỜNG (cổng, đường dẫn, chế độ LLM, khoá ký).
Mọi NGƯỠNG của phương pháp — blocking_w, hot_w, risk floor, band score,
theta, lambda — sống trong config/*.yaml, vì mỗi ngưỡng phải mang đủ ba vế:
chỗ ở duy nhất · suy ra từ đâu · điều kiện phải xem lại.

Đặt một ngưỡng vào đây là mất vế (ii) và (iii).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.contracts.errors import ConfigError

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent.parent

#: Giá trị mặc định của `jwt_secret` — CHỈ hợp lệ cho dev/test một máy. Đây là
#: hằng số công khai (nằm trong git), nên bất kỳ ai đọc được repo đều tự phát
#: được token `admin` nếu bản deploy vẫn dùng nguyên giá trị này. Xem
#: `Settings._fail_closed_khi_production_dung_secret_mac_dinh` bên dưới.
DEFAULT_JWT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CERTUS_", env_file=".env", extra="ignore"
    )

    # --- LLM ---
    llm_mode: Literal["mock", "live", "record"] = "mock"
    anthropic_api_key: str | None = None
    #: OAuth bearer thay cho api_key — để thu cassette bằng subscription (khi
    #: không có khoá API riêng). Chỉ dùng cho record/live; lớp học chạy mock.
    anthropic_auth_token: str | None = None
    model: str = "claude-opus-5"
    #: 8192 chứ không 4096: câu trả lời diễn giải bằng tiếng Việt (nhiều token/ký
    #: tự) kèm bảng ba-mẫu-số và nhiều claim từng vượt 4096 → JSON bị cắt cụt
    #: giữa chừng, parser mất sạch claim. max_tokens KHÔNG nằm trong cassette key
    #: nên nâng trần rồi thu lại ghi đè đúng file cũ.
    max_tokens: int = 8192

    # --- đường dẫn ---
    config_dir: Path = BACKEND_ROOT / "config"
    cassette_dir: Path = REPO_ROOT / "fixtures" / "cassettes"
    #: Artifact mutation precomputed (host chạy mutmut MỘT LẦN rồi commit JSON;
    #: pipeline replay, không chạy mutmut lúc phân tích). Xem observe.py.
    mutations_dir: Path = REPO_ROOT / "fixtures" / "mutations"
    targets_dir: Path = REPO_ROOT / "fixtures" / "targets"
    kb_dir: Path = REPO_ROOT / "kb"
    workspace_dir: Path = BACKEND_ROOT / "var" / "workspaces"
    ledger_path: Path = BACKEND_ROOT / "var" / "evidence.jsonl"
    db_path: Path = BACKEND_ROOT / "var" / "certus.sqlite3"
    log_dir: Path = BACKEND_ROOT / "var" / "logs"

    # --- auth ---
    # GIỚI HẠN — nói thẳng ở đây, không chỉ ở docstring `auth/jwt_auth.py`:
    # HS256 + secret này là WORKSHOP-ONLY, chạy trên một máy, KHÔNG phải mẫu
    # production. Production cần khoá bất đối xứng (RS256/EdDSA) và
    # `jwt_secret` không bao giờ mang một giá trị mặc định trong code.
    # Giữ default để dev/test cắm chạy ngay; `env="production"` (biến môi
    # trường `CERTUS_ENV`) mà vẫn giữ nguyên default thì fail-closed lúc khởi
    # động — xem `_fail_closed_khi_production_dung_secret_mac_dinh`.
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 8 * 3600

    # Môi trường chạy — KHÔNG phải một ngưỡng phương pháp, đây là cờ triển khai
    # thuộc về máy chủ đang chạy. "development"/"test" (mặc định) giữ được
    # `jwt_secret` mặc định để workshop chạy không cần cấu hình gì thêm.
    # Đặt `CERTUS_ENV=production` là lời khai "đây là request thật" — lúc đó
    # secret mặc định bị chặn, không đợi tới khi có ai khai thác được nó.
    env: str = "development"

    # --- upload ---
    # Trần TỔNG số byte đã giải nén trong MỘT lượt upload — chặn ca nhiều tệp
    # nhỏ dưới trần `data-policy.max_file_bytes` từng tệp nhưng cộng dồn thành
    # một vụ nổ bộ nhớ, và ca zip khai header nói dối (`zinfo.file_size` nhỏ,
    # giải nén ra lớn). Đây là trần TÀI NGUYÊN của máy chủ, không phải chính
    # sách nội dung — chính sách theo từng tệp vẫn sống ở `data-policy.yaml`.
    upload_max_total_bytes: int = 64 * 1024 * 1024

    # --- observability ---
    otlp_endpoint: str | None = None
    log_level: str = "INFO"

    # --- retrieval ---
    context_max_chars: int = 1200

    # --- sandbox ---
    # "subprocess" chạy được mọi nơi nhưng KHÔNG cô lập thật — nó chặn được
    # nhầm lẫn, không chặn được ý đồ. "docker" cô lập thật, cần Docker sẵn.
    # Đánh đổi có ý thức, không phải giới hạn bị bỏ quên: xem
    # docs/design/system-design.md §2.1.
    sandbox_mode: Literal["subprocess", "docker"] = "subprocess"
    sandbox_image: str = "python:3.12-slim"
    probe_timeout_seconds: int = 60

    def ensure_dirs(self) -> None:
        for p in (self.workspace_dir, self.log_dir, self.ledger_path.parent, self.db_path.parent):
            p.mkdir(parents=True, exist_ok=True)

    def jwt_secret_is_default(self) -> bool:
        """True nếu `jwt_secret` vẫn còn nguyên giá trị mặc định workshop-only.

        Hàm riêng thay vì so sánh trực tiếp ở nơi gọi: chỗ ở duy nhất của định
        nghĩa "thế nào là default", để không lệch nhau giữa validator dưới đây
        và bất kỳ chỗ nào khác sau này cần hỏi cùng câu hỏi.
        """
        return self.jwt_secret == DEFAULT_JWT_SECRET

    @model_validator(mode="after")
    def _fail_closed_khi_production_dung_secret_mac_dinh(self) -> "Settings":
        """`CERTUS_ENV=production` + secret mặc định ⇒ nổ ngay lúc khởi động.

        Không rơi về hành vi "chạy rồi tính sau": một secret công khai (nằm
        trong git) đang phục vụ request thật là một bản build đã lộ khoá ký
        token `admin` cho bất kỳ ai đọc được mã nguồn. Dev/test giữ nguyên
        default vì `env` mặc định là "development", không phải "production".
        """
        if self.env.strip().lower() == "production" and self.jwt_secret_is_default():
            raise ConfigError(
                "jwt_secret",
                "CERTUS_ENV=production nhưng jwt_secret vẫn là giá trị mặc định "
                f"workshop-only ({DEFAULT_JWT_SECRET!r}) — đặt CERTUS_JWT_SECRET "
                "thật trước khi khởi động",
            )
        return self


settings = Settings()
