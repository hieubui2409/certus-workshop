"""Nhận mã nguồn người dùng tải lên.

Đây là biên tin cậy của cả sản phẩm. Mọi thứ đi qua đây là **dữ liệu do người
ngoài kiểm soát**, kể cả khi nó trông như mã nguồn của một dự án nghiêm túc.
"""

from __future__ import annotations

import hashlib
import uuid
import zipfile

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.schemas import AcceptedFile, UploadAck
from app.api.deps import needs
from app.contracts.errors import CertusError
from app.policy.data_policy import load_policy
from app.settings import settings

router = APIRouter(prefix="/api", tags=["upload"])

MAX_FILES = 2000

#: Kích thước đọc mỗi khối khi giải nén một entry — giữ đỉnh bộ nhớ nhỏ và cố
#: định bất kể entry khai gì trong header, vì header là dữ liệu do người ngoài
#: kiểm soát (xem `_read_bounded`).
_READ_CHUNK_BYTES = 64 * 1024


def _read_bounded(zf: zipfile.ZipFile, name: str, limit: int) -> bytes:
    """Giải nén `name` theo từng khối, huỷ ngay khi vượt `limit`.

    Không tin `zinfo.file_size` khai trong header của entry: đó là số một
    zip-bomb có thể khai nhỏ trong khi luồng giải nén thật trả ra rất lớn.
    Đọc `zf.read(name)` một phát chặn được ca "header nói đúng và nói to"
    nhưng KHÔNG chặn được ca "header nói dối" — vòng đọc-theo-khối này chặn cả
    hai, vì nó đo byte thật đang chảy ra, không đo con số ai đó khai trước.
    """
    read = 0
    chunks: list[bytes] = []
    with zf.open(name) as fh:
        while True:
            chunk = fh.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            read += len(chunk)
            if read > limit:
                raise CertusError(
                    f"{name}: giải nén vượt trần {limit} byte (đã đọc {read})"
                )
            chunks.append(chunk)
    return b"".join(chunks)


@router.post("/upload", response_model=UploadAck)
async def upload(
    file: UploadFile = File(...), principal=Depends(needs("repo:read"))
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise CertusError("chỉ nhận tệp .zip")

    upload_id = uuid.uuid4().hex[:12]
    dest = settings.workspace_dir / upload_id
    dest.mkdir(parents=True, exist_ok=True)

    raw = dest / "_upload.zip"
    raw.write_bytes(await file.read())

    policy = load_policy()
    total_budget = settings.upload_max_total_bytes
    accepted: list[AcceptedFile] = []
    rejected: dict[str, str] = {}
    total = 0
    with zipfile.ZipFile(raw) as zf:
        names = zf.namelist()
        if len(names) > MAX_FILES:
            raise CertusError(f"{len(names)} tệp vượt trần {MAX_FILES}")
        for name in names:
            # Zip slip: một entry tên `../../x` ghi ra ngoài thư mục đích.
            target = (dest / name).resolve()
            if dest.resolve() not in target.parents and target != dest.resolve():
                rejected[name] = "đường dẫn thoát khỏi thư mục đích"
                continue
            if name.endswith("/"):
                continue

            # Zip bomb, lớp 1 — kiểm kích thước KHAI TRONG HEADER trước khi
            # giải nén một byte nào: một entry đã khai `file_size` vượt trần
            # `max_file_bytes` thì không có lý do đọc nó vào RAM để rồi vứt.
            declared_size = zf.getinfo(name).file_size
            decision = policy.decide(name, size_bytes=declared_size)
            if not decision.allowed:
                rejected[name] = decision.reason
                continue

            # Zip bomb, lớp 2 — trần TỔNG cho cả lượt upload: nhiều tệp mỗi
            # tệp dưới `max_file_bytes` vẫn cộng dồn thành một vụ nổ bộ nhớ.
            remaining_budget = total_budget - total
            if declared_size > remaining_budget:
                rejected[name] = (
                    f"tổng dung lượng giải nén vượt trần {total_budget} byte"
                )
                continue

            # Zip bomb, lớp 3 — không tin `declared_size`: đọc theo khối và
            # huỷ ngay khi byte THẬT vượt trần, phòng ca header khai nhỏ hơn
            # luồng giải nén thật.
            try:
                data = _read_bounded(
                    zf, name, min(policy.max_file_bytes, remaining_budget)
                )
            except CertusError as exc:
                rejected[name] = str(exc)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            total += len(data)
            # Băm BYTE THẬT vừa ghi ra đĩa, không băm gì khai trong header:
            # đây là neo duy nhất cho phép người dùng đối chiếu thứ CERTUS
            # nhận với thứ họ nén. Băm cái đã khai thì chỉ chứng minh header
            # tự nhất quán với chính nó.
            accepted.append(
                AcceptedFile(
                    path=name,
                    bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
    raw.unlink(missing_ok=True)

    return UploadAck(
        upload_id=upload_id,
        accepted=accepted,
        files_accepted=len(accepted),
        files_rejected=len(rejected),
        rejected_reasons=rejected,
        bytes_total=total,
    )
