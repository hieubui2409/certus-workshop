"""Hai câu hỏi về dữ liệu nhạy cảm, hai cơ chế khác nhau.

1. *"Mẫu chặn gồm những gì"* — `build_blocklist()`: luật lọc theo TÊN TỆP.
2. *"Chuỗi nào là bí mật"* — `find_secrets()` / `redact_text()`: luật lọc theo
   NỘI DUNG, không quan tâm tệp tên gì.

Hai lớp này bắt hai loại lỗi khác nhau: lọc theo tên bắt được `id_rsa` mà chưa
cần mở ra đọc; lọc theo nội dung bắt được một khoá Stripe dán nhầm vào
`README.md`. Không lớp nào thay được lớp kia.

Redaction theo nội dung phục vụ LỚP HIỂN THỊ và lớp lưu trữ do người đọc
(panel "tệp đã gửi cho mô hình", trích đoạn đính kèm evidence). Việc tệp nào
được đưa vào payload gửi cho mô hình do `data_policy.DataPolicy.select()`
quyết — xem `docs/design/sdd/06-platform.md` §3.3 để thấy đúng ranh giới.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Danh sách chặn theo tên tệp. Đây là HẰNG SỐ CODE, không phải giá trị mặc
#: định của config: nó là sàn của chính sách, không phải gợi ý khởi điểm.
DEFAULT_BLOCKLIST = ["*.env", "*.pem", "*_secret*", "credentials*", "*.key"]


@dataclass(frozen=True)
class SecretPattern:
    """Một mẫu bí mật. `name` đi vào chuỗi thay thế nên người đọc log biết
    ĐÃ CHE CÁI GÌ — một dãy `***` không phân biệt được "có bí mật ở đây" với
    "chỗ này vốn trống"."""

    name: str
    regex: re.Pattern[str]


def _p(name: str, pattern: str, flags: int = 0) -> SecretPattern:
    return SecretPattern(name=name, regex=re.compile(pattern, flags))


#: Thứ tự có ý nghĩa: mẫu hẹp (nhận diện được nhà cung cấp) đứng trước mẫu rộng
#: (gán biến chung chung), để nhãn trong chuỗi thay thế nói được càng nhiều
#: càng tốt.
SECRET_PATTERNS: list[SecretPattern] = [
    _p("stripe-live-key", r"sk_live_[A-Za-z0-9]{8,}"),
    _p("stripe-test-key", r"sk_test_[A-Za-z0-9]{8,}"),
    _p("private-key-block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    _p("private-key-header", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    _p("aws-access-key-id", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    _p("aws-secret-access-key", r"(?i)aws_secret_access_key\s*[=:]\s*\S+"),
    _p("github-token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    _p("github-pat", r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    _p("slack-token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    _p("bearer-token", r"(?i)authorization\s*:\s*bearer\s+\S+"),
    _p("password-assignment", r"(?i)\b[a-z0-9_]*(?:password|passwd|pwd)\s*[=:]\s*\S+"),
    _p("secret-assignment", r"(?i)\b[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|ACCESS_KEY)\s*[=:]\s*\S+"),
]


@dataclass(frozen=True)
class SecretHit:
    """Một lần khớp. Giữ `start`/`end` để UI tô được đúng đoạn, và giữ `preview`
    đã cắt cụt — bản thân báo cáo về bí mật không được chứa bí mật."""

    pattern: str
    start: int
    end: int
    preview: str


@dataclass(frozen=True)
class RedactionResult:
    text: str
    hits: list[SecretHit]

    @property
    def count(self) -> int:
        return len(self.hits)

    @property
    def clean(self) -> bool:
        return not self.hits


def build_blocklist(cfg: dict) -> list[str]:
    """Ghép danh sách chặn theo tên tệp từ hằng số code và cấu hình dự án.

    Dự án có hai đòn bẩy: `blocklist_override` cho trường hợp bộ mẫu mặc định
    không hợp với cách tổ chức tệp của dự án, và `blocklist_extra` cho mẫu
    riêng của dự án. Cả hai đều đi kèm ba vế trong `config/data-policy.yaml`.
    """
    patterns = list(DEFAULT_BLOCKLIST)
    if cfg.get("blocklist_override"):
        patterns = list(cfg["blocklist_override"])
    return patterns + list(cfg.get("blocklist_extra", []))


def find_secrets(text: str) -> list[SecretHit]:
    """Quét nội dung, trả về mọi đoạn khớp mẫu bí mật.

    Không dừng ở lần khớp đầu: đếm được bao nhiêu chỗ là mẫu số của câu
    "đã che N chỗ" — và một con số không có mẫu số thì không nói lên gì.
    """
    hits: list[SecretHit] = []
    for pattern in SECRET_PATTERNS:
        for m in pattern.regex.finditer(text):
            fragment = m.group(0)
            hits.append(
                SecretHit(
                    pattern=pattern.name,
                    start=m.start(),
                    end=m.end(),
                    preview=fragment[:4] + "…" if len(fragment) > 4 else "…",
                )
            )
    return sorted(hits, key=lambda h: (h.start, -h.end))


def redact_text(text: str, placeholder: str = "[REDACTED:{name}]") -> RedactionResult:
    """Thay mọi đoạn khớp bằng nhãn mang tên mẫu.

    Thay từ cuối lên đầu để offset của các lần khớp phía trước không bị dịch.
    Bỏ qua khớp nằm lồng trong một khớp đã xử lý (ví dụ `AKIA…` nằm trong một
    dòng `aws_secret_access_key=…`) — che hai lần không an toàn hơn, chỉ khó đọc hơn.
    """
    hits = find_secrets(text)
    # Chọn tập khớp KHÔNG chồng, ưu tiên khớp RỘNG (bao ngoài). Bản cũ duyệt
    # start giảm dần và bỏ khớp có `end > covered_from`: khi một khớp con (start
    # cao hơn) được áp trước, nó set covered_from thấp và làm khớp BAO NGOÀI bị
    # bỏ — nên thân private key còn nguyên văn mà `hits` vẫn báo "đã che". Đây là
    # ngược đúng ý: phải bỏ khớp NẰM TRONG, giữ khớp bao ngoài. Duyệt start tăng,
    # end giảm (find_secrets đã sắp vậy) nên khớp rộng đến trước; chỉ nhận khớp
    # bắt đầu ngoài vùng đã phủ.
    chosen: list[SecretHit] = []
    covered_until = -1
    for hit in sorted(hits, key=lambda h: (h.start, -h.end)):
        if hit.start >= covered_until:
            chosen.append(hit)
            covered_until = hit.end
    # Thay từ phải sang trái để offset các khớp phía trước không bị dịch.
    out = text
    for hit in sorted(chosen, key=lambda h: h.start, reverse=True):
        out = out[: hit.start] + placeholder.format(name=hit.pattern) + out[hit.end :]
    return RedactionResult(text=out, hits=sorted(chosen, key=lambda h: h.start))
