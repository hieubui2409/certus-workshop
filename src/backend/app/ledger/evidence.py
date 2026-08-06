"""Sổ bằng chứng append-only, nối bằng chuỗi sha256.

Mỗi dòng là một `LedgerRecord` (xem `app.contracts.types`): 5 trường nội dung
{claim_id, command, exit_code, output_sha256, verdict} cộng `prev_hash` và
`self_hash` để nối thành chuỗi.

GIỚI HẠN — nói thẳng, vì một giới hạn không được in ra sẽ bị đọc thành một bảo
đảm: chuỗi này là **tamper-EVIDENT**, KHÔNG phải **tamper-proof**. Ai ghi được
tệp thì tính lại được cả chuỗi từ dòng bị sửa trở đi và `verify_chain()` sẽ báo
xanh. Nó chứng minh "sổ đã bị sửa bởi người không biết luật hash", nó không
chứng minh "sổ không sửa được". Muốn tamper-proof thì cần thứ kẻ sửa tệp không
với tới: neo hash ra ngoài máy, hoặc ký bằng khoá cất ở nơi khác. CERTUS không
có thứ đó.

HIỆU NĂNG — tài liệu nền mang nợ chặn `B29` vì cài đặt cũ đọc lại TOÀN BỘ sổ ở
mỗi lần append để lấy `prev_hash`: 10.000 record mất 36,2 giây và chi phí phình
theo bình phương. Ở đây `prev_hash` giữ trong bộ nhớ, và lần đầu mở một sổ có
sẵn thì chỉ đọc ĐUÔI tệp (seek từ cuối, lùi từng khối cho tới dấu xuống dòng).
Append là O(1). `bytes_read` cộng dồn số byte thực đọc để test khẳng định được
điều đó bằng số chứ không bằng niềm tin.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel

from app.contracts.errors import CertusError
from app.contracts.types import LedgerRecord
from app.settings import settings

#: prev_hash của dòng đầu tiên. 64 số 0 — cùng độ dài với một sha256 thật nên
#: mọi chỗ so sánh độ dài không cần biết đến ca đặc biệt này.
GENESIS_HASH = "0" * 64

#: Khối đọc lùi khi dò dòng cuối. 4 KiB đủ chứa vài dòng record thực tế.
_TAIL_BLOCK = 4096

Verdict = Literal["executed-pass", "executed-fail", "UNVERIFIED"]

#: Năm trường nội dung + phần siêu dữ liệu tham gia vào hash. `self_hash` KHÔNG
#: nằm trong danh sách này — nó là kết quả, không phải đầu vào.
_HASHED_FIELDS = (
    "claim_id",
    "command",
    "exit_code",
    "output_sha256",
    "verdict",
    "ts",
    "actor",
    "prev_hash",
)


class LedgerCorruption(CertusError):
    """Một dòng của sổ không parse được hoặc không đúng khuôn.

    Fail-closed: sổ hỏng thì downstream không được "đọc phần còn đọc được" —
    một sổ đọc dở đọc y hệt một sổ đầy đủ nhưng ngắn hơn.
    """


class ChainCheck(BaseModel):
    """Kết quả `verify_chain()`.

    Có `records` (mẫu số) đi kèm `ok` vì "chuỗi hợp lệ" trên một sổ rỗng và
    trên một sổ 10.000 dòng là hai phát biểu rất khác nhau.
    """

    ok: bool
    records: int
    broken_at: int | None = None
    reason: str | None = None


def sha256_hex(data: str | bytes) -> str:
    """Băm nội dung output. Đây là thứ DUY NHẤT của output đi vào sổ."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: dict) -> str:
    """JSON tái lập được: khoá sort, không khoảng trắng thừa.

    Thứ tự khoá của `dict` là chi tiết cài đặt; một hash phụ thuộc chi tiết cài
    đặt là một hash không kiểm chứng lại được ở máy khác.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_self_hash(fields: dict) -> str:
    """sha256 trên đúng `_HASHED_FIELDS`. Thiếu trường nào ⇒ KeyError, không
    lặng lẽ băm một dict thiếu."""
    return sha256_hex(_canonical({k: fields[k] for k in _HASHED_FIELDS}))


def verdict_for(exit_code: int | None) -> Verdict:
    """Exit code LÀ câu trả lời — không có nhánh nào đọc stdout để đoán.

    `None` nghĩa là lệnh chưa từng chạy, và đó là `UNVERIFIED`: một phán quyết
    hợp lệ, không phải một thất bại. Ánh xạ nó thành `executed-fail` sẽ trộn
    "đã chạy và hỏng" với "chưa từng chạy".
    """
    if exit_code is None:
        return "UNVERIFIED"
    return "executed-pass" if exit_code == 0 else "executed-fail"


class EvidenceLedger:
    """Sổ JSONL append-only. Không có API nào sửa hoặc xoá một dòng đã ghi."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else Path(settings.ledger_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash: str | None = None
        self._bytes_read = 0
        # Sổ là hash-chain: mỗi dòng neo vào prev_hash của dòng trước. Đọc
        # prev_hash → dựng record → ghi phải là MỘT thao tác không thể chen. Nếu
        # không, hai luồng (FastAPI chạy endpoint sync trong threadpool, cùng
        # dùng get_ledger() singleton) cùng đọc một prev_hash rồi ghi hai dòng
        # cùng neo → verify_chain gãy. Đo được: 8 luồng → 5/5 lượt ok=False.
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- đọc đuôi

    @property
    def path(self) -> Path:
        return self._path

    @property
    def bytes_read(self) -> int:
        """Số byte thực sự đọc từ đĩa trong vòng đời đối tượng này.

        Tồn tại để đối chứng nợ `B29`: append thứ hai trở đi phải cộng thêm 0.
        """
        return self._bytes_read

    def _read_last_line(self) -> str | None:
        """Đọc dòng cuối bằng cách lùi từ cuối tệp, KHÔNG đọc từ đầu.

        Chi phí O(độ dài một dòng), không phụ thuộc số dòng đã có.
        """
        if not self._path.exists():
            return None
        size = self._path.stat().st_size
        if size == 0:
            return None
        with self._path.open("rb") as fh:
            block = _TAIL_BLOCK
            while True:
                start = max(0, size - block)
                fh.seek(start)
                chunk = fh.read(size - start)
                self._bytes_read += len(chunk)
                stripped = chunk.rstrip(b"\n")
                idx = stripped.rfind(b"\n")
                if idx != -1:
                    return stripped[idx + 1 :].decode("utf-8")
                if start == 0:
                    # Cả tệp chỉ có đúng một dòng.
                    return stripped.decode("utf-8") or None
                block *= 2

    def _load_last_hash(self) -> str:
        """`prev_hash` cho lần append tiếp theo.

        Lần đầu đọc đuôi tệp; từ lần sau lấy thẳng trong bộ nhớ.
        """
        if self._last_hash is not None:
            return self._last_hash
        line = self._read_last_line()
        if line is None:
            self._last_hash = GENESIS_HASH
            return self._last_hash
        try:
            self._last_hash = str(json.loads(line)["self_hash"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise LedgerCorruption(
                f"dòng cuối của {self._path} không đọc được self_hash: {exc}"
            ) from exc
        return self._last_hash

    # ------------------------------------------------------------------- ghi

    def append(
        self,
        *,
        claim_id: str,
        command: str,
        exit_code: int | None,
        output: str | bytes | None = None,
        output_sha256: str | None = None,
        actor: str | None = None,
        verdict: Verdict | None = None,
    ) -> str:
        """Ghi một dòng, trả về `evidence_id`.

        `evidence_id` CHÍNH LÀ `self_hash` — không có bảng id riêng, vì một id
        do bộ đếm cấp thì hai sổ khác nội dung vẫn trùng id, còn hash thì không.
        Đây là chuỗi mà `Claim.evidence_ids` viện dẫn.
        """
        return self.append_record(
            claim_id=claim_id,
            command=command,
            exit_code=exit_code,
            output=output,
            output_sha256=output_sha256,
            actor=actor,
            verdict=verdict,
        ).self_hash

    def append_record(
        self,
        *,
        claim_id: str,
        command: str,
        exit_code: int | None,
        output: str | bytes | None = None,
        output_sha256: str | None = None,
        actor: str | None = None,
        verdict: Verdict | None = None,
    ) -> LedgerRecord:
        """Như `append()` nhưng trả về cả dòng vừa ghi. O(1): không đọc lại sổ.

        Truyền `output` (băm hộ) hoặc `output_sha256` (đã băm sẵn). Không có
        cái nào ⇒ băm chuỗi rỗng, để trường không bao giờ trống — một
        `output_sha256` rỗng đọc lẫn với "chưa tính".
        """
        if output is not None and output_sha256 is not None:
            raise ValueError("truyền output HOẶC output_sha256, không truyền cả hai")
        digest = output_sha256 if output_sha256 is not None else sha256_hex(output or "")

        # Toàn bộ đọc-prev → dựng → ghi → cập-nhật-last nằm trong một khoá: đây
        # là đoạn tới hạn của hash-chain, chen vào giữa là làm đứt chuỗi.
        with self._lock:
            prev_hash = self._load_last_hash()
            fields = {
                "claim_id": claim_id,
                "command": command,
                "exit_code": exit_code,
                "output_sha256": digest,
                "verdict": verdict or verdict_for(exit_code),
                "ts": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                "prev_hash": prev_hash,
            }
            record = LedgerRecord(**fields, self_hash=compute_self_hash(fields))

            line = record.model_dump_json() + "\n"
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())

            self._last_hash = record.self_hash
        return record

    # ------------------------------------------------------------------ đọc

    def _iter_lines(self) -> Iterable[tuple[int, str]]:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for i, raw in enumerate(fh):
                self._bytes_read += len(raw.encode("utf-8"))
                line = raw.strip()
                if line:
                    yield i, line

    def read_all(self) -> list[LedgerRecord]:
        """Đọc cả sổ — O(n), và chỉ dùng cho việc bản chất là O(n)."""
        out: list[LedgerRecord] = []
        for i, line in self._iter_lines():
            try:
                out.append(LedgerRecord.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001 — bọc lại, không nuốt
                raise LedgerCorruption(f"{self._path}:{i + 1} không parse được: {exc}") from exc
        return out

    def tail(self, n: int = 20) -> list[LedgerRecord]:
        """N dòng cuối, cho panel UI. Vẫn quét tệp — dùng để hiển thị, không
        dùng trong đường ghi."""
        return self.read_all()[-n:]

    def get(self, self_hash: str) -> LedgerRecord | None:
        """Tra một record theo `self_hash` — đây chính là `evidence_id` mà
        `Claim.evidence_ids` viện dẫn."""
        for rec in self.read_all():
            if rec.self_hash == self_hash:
                return rec
        return None

    # --------------------------------------------------------------- kiểm tra

    def verify_chain(self) -> ChainCheck:
        """Duyệt cả sổ, kiểm hai điều ở mỗi dòng: `self_hash` tính lại có khớp,
        và `prev_hash` có bằng `self_hash` dòng trước.

        O(n) đúng bản chất, và cố ý KHÔNG chạy trong `append()` — gọi nó ở đó
        chính là cách nợ `B29` ra đời.
        """
        prev = GENESIS_HASH
        count = 0
        for i, line in self._iter_lines():
            try:
                rec = LedgerRecord.model_validate_json(line)
            except Exception as exc:  # noqa: BLE001
                return ChainCheck(
                    ok=False, records=count, broken_at=i, reason=f"không parse được: {exc}"
                )
            count += 1
            if rec.prev_hash != prev:
                return ChainCheck(
                    ok=False,
                    records=count,
                    broken_at=i,
                    reason=f"prev_hash lệch: chờ {prev[:12]}…, thấy {rec.prev_hash[:12]}…",
                )
            recomputed = compute_self_hash(rec.model_dump(mode="json"))
            if recomputed != rec.self_hash:
                return ChainCheck(
                    ok=False,
                    records=count,
                    broken_at=i,
                    reason=(
                        f"self_hash không khớp nội dung: tính ra {recomputed[:12]}…, "
                        f"ghi {rec.self_hash[:12]}… — dòng này đã bị sửa sau khi ghi"
                    ),
                )
            prev = rec.self_hash
        return ChainCheck(ok=True, records=count)


_default_ledger: EvidenceLedger | None = None


def get_ledger() -> EvidenceLedger:
    """Sổ dùng chung theo cấu hình.

    Tầng trên gọi hàm này thay vì tự dựng `EvidenceLedger`, để cả tiến trình
    chỉ có MỘT chỗ giữ `prev_hash` trong bộ nhớ — hai đối tượng cùng trỏ vào
    một tệp sẽ cùng tin rằng mình biết dòng cuối là gì.

    Dựng lười: mở tệp và tạo thư mục không nên xảy ra ở thời điểm import.
    """
    global _default_ledger
    if _default_ledger is None:
        _default_ledger = EvidenceLedger()
    return _default_ledger
