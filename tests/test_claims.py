"""Kiểm việc parse claim từ output của model."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.claims import ClaimParseError, extract_claims_json, parse_claims  # noqa: E402
from app.contracts.types import Label  # noqa: E402


# ─────────────────────────── moi JSON ───────────────────────────


def test_extract_reads_a_bare_json_object():
    raw = extract_claims_json('{"nonce": "abc", "claims": []}')
    assert raw["nonce"] == "abc"


def test_extract_reads_json_inside_a_code_fence():
    text = 'Đây là kết quả:\n```json\n{"nonce": "abc", "claims": []}\n```\nHết.'
    assert extract_claims_json(text)["nonce"] == "abc"


def test_extract_reads_json_surrounded_by_prose():
    text = 'Tôi đã phân tích xong. {"nonce": "z9", "claims": []} Chúc bạn một ngày tốt.'
    assert extract_claims_json(text)["nonce"] == "z9"


def test_extract_handles_braces_inside_strings():
    text = '{"nonce": "n1", "answer": "dùng cú pháp {{NONCE}} nhé", "claims": []}'
    assert extract_claims_json(text)["answer"] == "dùng cú pháp {{NONCE}} nhé"


def test_extract_raises_when_there_is_no_json():
    with pytest.raises(ClaimParseError):
        extract_claims_json("Xin lỗi, tôi không chắc về điều đó.")


def test_extract_raises_on_broken_json():
    with pytest.raises(ClaimParseError):
        extract_claims_json('{"claims": [ }')


# ─────────────────────────── parse_claims ───────────────────────────


def test_parse_builds_claims_with_id_text_and_label():
    raw = {
        "claims": [
            {"id": "c1", "text": "Bộ kiểm chạm 412 dòng.", "label": "OBSERVED"},
            {"id": "c2", "text": "Zone chặn còn ô unknown.", "label": "DERIVED"},
        ]
    }
    claims = parse_claims(raw)

    assert [c.id for c in claims] == ["c1", "c2"]
    assert claims[0].text == "Bộ kiểm chạm 412 dòng."
    assert claims[0].label is Label.OBSERVED
    assert claims[1].label is Label.DERIVED


def test_parse_keeps_evidence_ids_and_anchors():
    raw = {
        "claims": [
            {
                "id": "c1",
                "text": "pytest thoát với mã 0.",
                "label": "OBSERVED",
                "evidence_ids": ["ev-01", "ev-02"],
                "anchors": [{"kind": "command", "ref": "pytest -q", "exit_code": 0}],
                "flags": ["n-too-small"],
            }
        ]
    }
    claim = parse_claims(raw)[0]

    assert claim.evidence_ids == ["ev-01", "ev-02"]
    assert claim.anchors[0].kind == "command"
    assert claim.anchors[0].ref == "pytest -q"
    assert claim.anchors[0].exit_code == 0
    assert claim.flags == ["n-too-small"]


def test_parse_builds_the_interval_object_for_a_rate_claim():
    raw = {
        "claims": [
            {
                "id": "c1",
                "text": "3/3 ô đạt band high.",
                "label": "OBSERVED",
                "is_rate": True,
                "k": 3,
                "n": 3,
                "interval": {
                    "lower": 0.4385,
                    "upper": 1.0,
                    "n": 3,
                    "k": 3,
                    "method": "wilson",
                    "saturated": True,
                },
                "anchors": [{"kind": "artifact", "ref": "sha256:abc"}],
            }
        ]
    }
    claim = parse_claims(raw)[0]

    assert claim.is_rate is True
    assert claim.interval is not None
    assert claim.interval.lower == pytest.approx(0.4385)
    assert claim.interval.saturated is True
    assert claim.interval.width == pytest.approx(1.0 - 0.4385)


def test_parse_fills_defaults_for_omitted_optional_fields():
    claim = parse_claims({"claims": [{"id": "c1", "text": "…", "label": "ASSUMED"}]})[0]

    assert claim.k is None
    assert claim.n is None
    assert claim.interval is None
    assert claim.evidence_ids == []
    assert claim.anchors == []
    assert claim.flags == []
    assert claim.is_rate is False
    assert claim.mechanism is None


def test_parse_accepts_an_empty_claim_list():
    assert parse_claims({"claims": []}) == []


# ─────────────────────────── từ chối đầu vào hỏng ───────────────────────────


def test_parse_rejects_a_label_outside_the_four_label_system():
    raw = {"claims": [{"id": "c1", "text": "…", "label": "VERIFIED"}]}
    with pytest.raises(ClaimParseError) as excinfo:
        parse_claims(raw)
    message = str(excinfo.value)
    assert "VERIFIED" in message
    assert "OBSERVED" in message  # nêu ra tập giá trị hợp lệ


def test_parse_rejects_a_claim_missing_a_required_field():
    with pytest.raises(ClaimParseError):
        parse_claims({"claims": [{"id": "c1", "label": "PRIOR"}]})


def test_parse_rejects_output_without_a_claims_array():
    with pytest.raises(ClaimParseError):
        parse_claims({"nonce": "abc", "answer": "…"})


def test_parse_rejects_a_non_object_entry():
    with pytest.raises(ClaimParseError):
        parse_claims({"claims": ["chỉ là một chuỗi"]})


# ───────────── `flags` mô hình viết sai khuôn (đo trên cassette thật) ─────────────


def _one(**over):
    """Một claim tối thiểu hợp lệ, cho phép đè từng trường."""
    return {
        "claims": [
            {
                "id": "c1",
                "text": "…",
                "label": "DERIVED",
                "evidence_ids": ["artifact.grid_coverage"],
                **over,
            }
        ]
    }


def test_flags_dang_chuoi_van_giu_nguyen():
    (claim,) = parse_claims(_one(flags=["needs_kb:house/risk-bands.md"]))
    assert claim.flags == ["needs_kb:house/risk-bands.md"]


def test_mechanism_bi_nhet_vao_flags_duoc_vot_len_dung_cho():
    """Đo được trên `analyze__6dd1265c847a.json`: mô hình viết
    `"flags": [{"mechanism": "Đối chiếu số ô unknown = 8 …"}]`.

    Nội dung đúng, chỗ để sai. Nó phải thành `claim.mechanism` để giao diện in
    ra dòng "cơ chế: …", chứ không phải một badge object vô nghĩa — và tuyệt
    đối không được làm chết cả lượt phân tích.
    """
    (claim,) = parse_claims(_one(flags=[{"mechanism": "Đối chiếu số ô unknown = 8."}]))
    assert claim.mechanism == "Đối chiếu số ô unknown = 8."
    assert claim.flags == []


def test_mechanism_dat_dung_cho_thang_cai_dat_nham_cho():
    (claim,) = parse_claims(
        _one(mechanism="đúng chỗ", flags=[{"mechanism": "nhầm chỗ"}])
    )
    assert claim.mechanism == "đúng chỗ"
    assert claim.flags == ["mechanism:nhầm chỗ"]


def test_co_dang_object_bi_ep_ve_quy_uoc_khoa_gia_tri():
    """`flags` trong repo vốn đã dùng `khoá:giá trị` (`na_reason:legacy_exempt`),
    nên một cờ viết dạng object ép về đúng quy ước đó thay vì bị vứt."""
    (claim,) = parse_claims(_one(flags=[{"na_reason": "legacy_exempt"}]))
    assert claim.flags == ["na_reason:legacy_exempt"]


def test_flags_khong_phai_list_van_khong_lam_chet_luot_phan_tich():
    (claim,) = parse_claims(_one(flags="một chuỗi trần"))
    assert claim.flags == ["một chuỗi trần"]
    (claim,) = parse_claims(_one(flags=[42, None]))
    assert claim.flags == ["42", "None"]
