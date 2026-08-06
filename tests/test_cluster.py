"""Test cho `app.core.stats.cluster`.

Câu hỏi mà mọi test ở đây phục vụ: "100 mẫu từ mấy nguồn?". Nếu module này
sai theo hướng dễ dãi thì mọi con số phía trên nó đều hẹp giả, và hẹp giả là
dạng sai nguy hiểm hơn hẳn rộng thật.

Neo: docs/research-notes/01-confidence-intervals.md §1.5, §4.2, §5.B
     docs/design/sdd/01-core-stats.md §4
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.stats.cluster import cluster_adjusted, icc_anova  # noqa: E402


# ═════════════════════════════ icc_anova ═══════════════════════════════════


def test_icc_anova_matches_research_note_anchor():
    stats = icc_anova([(20, 20), (20, 20), (19, 20), (8, 20), (5, 20)])
    assert stats is not None
    assert stats["icc"] == pytest.approx(0.5619, abs=1e-4)
    assert stats["msb"] == pytest.approx(2.665, abs=1e-6)
    assert stats["msw"] == pytest.approx(0.100, abs=1e-6)
    assert stats["n0"] == pytest.approx(20.0, abs=1e-9)
    assert stats["p_bar"] == pytest.approx(0.72, abs=1e-12)


def test_icc_anova_returns_none_below_two_clusters():
    """K<2 là câu hỏi sai, không phải dữ liệu hỏng — trả None, KHÔNG raise."""
    assert icc_anova([]) is None
    assert icc_anova([(8, 10)]) is None


def test_icc_anova_returns_none_when_within_variance_has_no_degrees_of_freedom():
    """Mỗi cluster đúng 1 mẫu thì MSW không tồn tại. Không được đoán."""
    assert icc_anova([(1, 1), (0, 1), (1, 1)]) is None


def test_icc_anova_clamps_negative_icc_to_zero_and_says_so():
    """MSB < MSW cho ICC âm. Clamp về 0 nhưng phải để lại dấu vết."""
    stats = icc_anova([(5, 10), (5, 10), (5, 10)])
    assert stats is not None
    assert stats["icc"] == 0.0
    assert stats["icc_raw"] < 0.0
    assert stats["clamped"] is True
    assert any("clamp" in w for w in stats["warnings"])


def test_icc_anova_never_returns_negative():
    for clusters in ([(5, 10)] * 4, [(3, 6), (3, 6), (4, 6), (2, 6)], [(0, 4)] * 3):
        stats = icc_anova(clusters)
        assert stats is not None
        assert stats["icc"] >= 0.0


def test_icc_anova_degenerate_data_takes_maximum_penalty():
    """Không có phương sai ở đâu cả -> ICC không xác định. Chọn phía an toàn."""
    stats = icc_anova([(20, 20)] * 5)
    assert stats is not None
    assert stats["degenerate"] is True
    assert stats["icc"] == 1.0
    assert any("phạt tối đa" in w for w in stats["warnings"])


def test_icc_anova_upper_bound_is_above_point_estimate():
    stats = icc_anova([(20, 20), (20, 20), (19, 20), (8, 20), (5, 20)])
    assert stats is not None
    assert stats["icc_upper"] >= stats["icc"]
    assert stats["icc_lower"] is not None
    assert stats["icc_lower"] <= stats["icc"]


def test_icc_anova_rejects_empty_cluster():
    """Cluster n=0 sẽ thổi phồng K và có thể làm route nhảy sai bậc."""
    with pytest.raises(ValueError):
        icc_anova([(0, 0), (5, 10)])


def test_icc_anova_rejects_malformed_input():
    with pytest.raises(ValueError):
        icc_anova([(11, 10), (5, 10)])
    with pytest.raises(ValueError):
        icc_anova([(5,), (5, 10)])
    with pytest.raises(TypeError):
        icc_anova([(0.5, 10), (5, 10)])


# ══════════════════════════ route selection ════════════════════════════════


def test_route_is_cluster_floor_below_ten_sources():
    """K=5 phải rơi cluster-floor, TUYỆT ĐỐI không phải icc."""
    out = cluster_adjusted([(20, 20), (20, 20), (19, 20), (8, 20), (5, 20)])
    assert out["route"] == "cluster-floor"
    assert out["cluster_floor"] is True
    assert out["n_eff"] == 5.0
    assert out["icc_used"] is None


def test_route_is_icc_upper_between_ten_and_twenty():
    out = cluster_adjusted([(4, 5)] * 12)
    assert out["route"] == "icc-upper"
    assert out["icc_used"] == out["icc_upper"]


def test_route_is_icc_at_twenty_or_more():
    out = cluster_adjusted([(4, 5)] * 25)
    assert out["route"] == "icc"
    assert out["icc_used"] == out["icc"]


@pytest.mark.parametrize("K,expected", [(1, "cluster-floor"), (9, "cluster-floor"),
                                        (10, "icc-upper"), (19, "icc-upper"),
                                        (20, "icc"), (47, "icc")])
def test_route_boundaries_are_decided_by_k_alone(K, expected):
    """Route do K quyết định, không do ai khai — kể cả khi dữ liệu y hệt nhau."""
    assert cluster_adjusted([(4, 5)] * K)["route"] == expected


def test_route_falls_back_to_floor_loudly_when_icc_cannot_be_estimated():
    """Đủ cluster về số lượng nhưng mỗi cluster 1 mẫu: phải hạ route và NÓI RA."""
    out = cluster_adjusted([(1, 1)] * 25)
    assert out["route"] == "cluster-floor"
    assert any("hạ về cluster-floor" in w for w in out["warnings"])


# ══════════════════ hiệu chỉnh: rộng hơn, không hẹp hơn ════════════════════


def test_clustering_correction_never_narrows_the_interval():
    """Hiệu chỉnh clustering chỉ được làm interval RỘNG ra."""
    for clusters in ([(20, 20), (20, 20), (19, 20), (8, 20), (5, 20)],
                     [(4, 5)] * 12,
                     [(18, 20), (12, 20), (20, 20)] * 8):
        out = cluster_adjusted(clusters)
        assert out["width"] >= out["naive_width"] - 1e-12
        assert out["lower"] <= out["naive_lower"] + 1e-12


def test_few_sources_cost_more_than_many_sources_at_equal_n():
    """Cùng 100 mẫu: 2 nguồn phải cho interval rộng hơn hẳn 50 nguồn."""
    many = cluster_adjusted([(9, 10)] * 10 + [(8, 10)] * 10)
    few = cluster_adjusted([(45, 50), (40, 50)])
    assert few["n_eff"] < many["n_eff"]
    assert few["width"] > many["width"]


def test_hard_ceiling_on_effective_n():
    """Trần n_eff <= K/ICC: thêm mẫu từ cùng nguồn không mua thêm được gì."""
    clusters = [(20, 20)] * 12 + [(0, 20)] * 13
    out = cluster_adjusted(clusters)
    assert out["route"] == "icc"
    assert out["icc_used"] is not None and out["icc_used"] > 0
    assert out["n_eff"] <= out["K"] / out["icc_used"] + 1e-9


def test_more_samples_from_same_sources_hits_diminishing_returns():
    small = cluster_adjusted([(18, 20), (12, 20), (20, 20), (5, 20), (16, 20)])
    big = cluster_adjusted([(180, 200), (120, 200), (200, 200), (50, 200), (160, 200)])
    # cluster-floor: n_eff bị chốt ở K bất kể mỗi cluster có bao nhiêu mẫu.
    assert small["n_eff"] == big["n_eff"] == 5.0


# ═══════════════════════ cờ phải lên tiếng ═════════════════════════════════


def test_cluster_floor_is_written_into_the_returned_dict_and_the_interval():
    out = cluster_adjusted([(20, 20), (20, 20), (19, 20), (8, 20), (5, 20)])
    assert out["cluster_floor"] is True
    assert out["interval"].route == "cluster-floor"
    assert out["interval"].n_eff == 5.0
    assert any("cluster-floor" in w and "CẤM ước ICC" in w for w in out["warnings"])


def test_warnings_are_sentences_not_codes():
    out = cluster_adjusted([(4, 5)] * 12)
    assert out["warnings"], "route icc-upper phải nói ra rằng nó đang bảo thủ"
    for w in out["warnings"]:
        assert len(w.split()) >= 4


def test_saturated_flag_survives_the_correction():
    out = cluster_adjusted([(20, 20)] * 25)
    assert out["saturated"] is True
    assert out["interval"].saturated is True


def test_invalid_conf_raises():
    with pytest.raises(ValueError):
        cluster_adjusted([(4, 5)] * 25, conf=1.0)
