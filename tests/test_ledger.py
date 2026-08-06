"""Sổ bằng chứng: chuỗi hash, phát hiện sửa trộm, và chi phí append.

Test ở đây khẳng định hai thứ khác hẳn nhau:
  * TÍNH ĐÚNG — chuỗi nối đúng, sửa một dòng thì lộ ra.
  * CHI PHÍ   — append là O(1). Đây không phải chuyện thẩm mỹ: cài đặt cũ trong
    tài liệu nền đọc lại cả sổ mỗi lần append và mất 36,2 giây cho 10.000
    record (nợ chặn B29). Một test đo được điều đó là cách duy nhất để nó không
    quay lại trong im lặng.
"""

from __future__ import annotations

import json

import pytest

from app.ledger.evidence import (
    GENESIS_HASH,
    ChainCheck,
    EvidenceLedger,
    LedgerCorruption,
    compute_self_hash,
    sha256_hex,
    verdict_for,
)
from app.settings import settings


@pytest.fixture()
def ledger(tmp_path) -> EvidenceLedger:
    return EvidenceLedger(tmp_path / "evidence.jsonl")


# ------------------------------------------------------------------ ghi & đọc


def test_append_ghi_du_nam_truong_va_hai_hash(ledger: EvidenceLedger) -> None:
    rec = ledger.append_record(
        claim_id="claim:1", command="pytest -q", exit_code=0, output="12 passed"
    )
    assert rec.claim_id == "claim:1"
    assert rec.command == "pytest -q"
    assert rec.exit_code == 0
    assert rec.output_sha256 == sha256_hex("12 passed")
    assert rec.verdict == "executed-pass"
    assert rec.prev_hash == GENESIS_HASH
    assert len(rec.self_hash) == 64


def test_verdict_suy_ra_tu_exit_code() -> None:
    # exit code LÀ câu trả lời; None nghĩa là chưa từng chạy, không phải "hỏng".
    assert verdict_for(0) == "executed-pass"
    assert verdict_for(1) == "executed-fail"
    assert verdict_for(None) == "UNVERIFIED"


def test_khong_co_exit_code_thi_la_unverified(ledger: EvidenceLedger) -> None:
    rec = ledger.append_record(claim_id="claim:2", command="đọc tài liệu", exit_code=None)
    assert rec.verdict == "UNVERIFIED"


def test_append_tra_ve_evidence_id_chinh_la_self_hash(ledger: EvidenceLedger) -> None:
    """`evidence_id` mà `Claim.evidence_ids` viện dẫn PHẢI tra ngược được về
    đúng dòng sổ — nếu không, một claim có neo và một claim neo vào hư không
    đọc giống hệt nhau."""
    evidence_id = ledger.append(claim_id="claim:1", command="pytest -q", exit_code=0)
    assert isinstance(evidence_id, str)
    assert len(evidence_id) == 64
    assert ledger.get(evidence_id).claim_id == "claim:1"


def test_get_ledger_tra_ve_dung_mot_doi_tuong(monkeypatch, tmp_path) -> None:
    """Hai đối tượng cùng trỏ vào một tệp sẽ cùng tin rằng mình biết dòng cuối
    là gì — nên tầng trên phải dùng chung một sổ."""
    import app.ledger.evidence as evidence_mod

    monkeypatch.setattr(evidence_mod, "_default_ledger", None)
    monkeypatch.setattr(settings, "ledger_path", tmp_path / "evidence.jsonl")
    assert evidence_mod.get_ledger() is evidence_mod.get_ledger()


def test_chuoi_hash_noi_lien_nhau(ledger: EvidenceLedger) -> None:
    recs = [
        ledger.append_record(claim_id=f"claim:{i}", command="pytest -q", exit_code=0, output=str(i))
        for i in range(5)
    ]
    assert recs[0].prev_hash == GENESIS_HASH
    for prev, cur in zip(recs, recs[1:]):
        assert cur.prev_hash == prev.self_hash


def test_verify_chain_xanh_tren_so_lanh(ledger: EvidenceLedger) -> None:
    for i in range(10):
        ledger.append_record(claim_id=f"claim:{i}", command="pytest -q", exit_code=i % 2, output=str(i))
    check = ledger.verify_chain()
    assert isinstance(check, ChainCheck)
    assert check.ok is True
    assert check.records == 10  # mẫu số đi kèm phán quyết, không chỉ mỗi cờ ok
    assert check.broken_at is None


def test_verify_chain_tren_so_rong(ledger: EvidenceLedger) -> None:
    check = ledger.verify_chain()
    assert check.ok is True
    assert check.records == 0


def test_get_va_read_all(ledger: EvidenceLedger) -> None:
    ledger.append_record(claim_id="claim:a", command="pytest", exit_code=0)
    b = ledger.append_record(claim_id="claim:b", command="coverage", exit_code=0)
    assert [r.claim_id for r in ledger.read_all()] == ["claim:a", "claim:b"]
    assert ledger.get(b.self_hash).claim_id == "claim:b"
    assert ledger.get("khong-ton-tai") is None


def test_append_khong_bao_gio_ghi_de(tmp_path) -> None:
    path = tmp_path / "evidence.jsonl"
    first = EvidenceLedger(path)
    first.append_record(claim_id="claim:1", command="pytest", exit_code=0)
    # Một đối tượng ledger MỚI trên cùng tệp phải nối tiếp, không bắt đầu lại.
    second = EvidenceLedger(path)
    rec = second.append_record(claim_id="claim:2", command="pytest", exit_code=0)
    assert rec.prev_hash != GENESIS_HASH
    assert second.verify_chain().records == 2


# ---------------------------------------------------------- tamper-EVIDENT


def test_sua_noi_dung_mot_dong_thi_lo_ra(ledger: EvidenceLedger) -> None:
    for i in range(3):
        ledger.append_record(claim_id=f"claim:{i}", command="pytest -q", exit_code=1, output=str(i))

    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    doctored = json.loads(lines[1])
    doctored["verdict"] = "executed-pass"  # đổi fail thành pass, giữ nguyên hash
    lines[1] = json.dumps(doctored, ensure_ascii=False)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    check = ledger.verify_chain()
    assert check.ok is False
    assert check.broken_at == 1
    assert "self_hash" in (check.reason or "")


def test_xoa_mot_dong_giua_so_thi_lo_ra(ledger: EvidenceLedger) -> None:
    for i in range(4):
        ledger.append_record(claim_id=f"claim:{i}", command="pytest", exit_code=0, output=str(i))
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    del lines[2]
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    check = ledger.verify_chain()
    assert check.ok is False
    assert "prev_hash" in (check.reason or "")


def test_ghi_lai_ca_chuoi_thi_KHONG_lo_ra(ledger: EvidenceLedger) -> None:
    """Giới hạn phải kiểm chứng được, không chỉ nằm trong docstring.

    Kẻ ghi được tệp và biết luật hash sẽ dựng lại cả chuỗi và verify_chain báo
    xanh. Đó đúng là ranh giới giữa tamper-EVIDENT và tamper-proof.
    """
    for i in range(3):
        ledger.append_record(claim_id=f"claim:{i}", command="pytest", exit_code=1, output=str(i))

    rows = [json.loads(line) for line in ledger.path.read_text(encoding="utf-8").splitlines()]
    rows[1]["verdict"] = "executed-pass"
    prev = GENESIS_HASH
    for row in rows:
        row["prev_hash"] = prev
        row["self_hash"] = compute_self_hash(row)
        prev = row["self_hash"]
    ledger.path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )

    assert ledger.verify_chain().ok is True  # chuỗi hợp lệ, nội dung đã bị đổi


def test_so_hong_thi_no_chu_khong_doc_do_dang(tmp_path) -> None:
    path = tmp_path / "evidence.jsonl"
    path.write_text("{đây không phải json}\n", encoding="utf-8")
    with pytest.raises(LedgerCorruption):
        EvidenceLedger(path).read_all()


# ------------------------------------------------------- chi phí append (B29)


def test_append_khong_doc_lai_so__doi_chung_B29(tmp_path) -> None:
    """Append thứ 2 trở đi phải đọc ĐÚNG 0 byte.

    Đây là phát biểu chính xác của "O(1)": không phải "nhanh", mà là "chi phí
    không phụ thuộc số record đã có".
    """
    led = EvidenceLedger(tmp_path / "evidence.jsonl")
    led.append_record(claim_id="claim:0", command="pytest -q", exit_code=0, output="x")
    baseline = led.bytes_read  # sổ rỗng lúc mở nên baseline vốn đã là 0

    for i in range(1, 1000):
        led.append_record(claim_id=f"claim:{i}", command="pytest -q", exit_code=0, output=str(i))

    assert led.bytes_read == baseline
    assert led.path.stat().st_size > 100_000  # sổ đã thực sự lớn


def test_mo_so_co_san_chi_doc_duoi_tep(tmp_path) -> None:
    path = tmp_path / "evidence.jsonl"
    writer = EvidenceLedger(path)
    for i in range(2000):
        writer.append_record(claim_id=f"claim:{i}", command="pytest -q", exit_code=0, output=str(i))
    size = path.stat().st_size

    reopened = EvidenceLedger(path)
    reopened.append_record(claim_id="claim:tiep", command="pytest -q", exit_code=0)

    assert 0 < reopened.bytes_read < size / 10  # đọc đuôi, không đọc cả sổ
    assert reopened.verify_chain().ok is True
