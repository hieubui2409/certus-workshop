"""Hiệu chỉnh clustering — vì 100 mẫu từ 6 nguồn không phải là 100 mẫu.

Vì sao module này tồn tại: đã đo được ca 100 trang lấy từ 6 case file, và
interval thật rộng gấp 8.3 lần interval tính như thể 100 mẫu độc lập. Con số
"n" trơ trọi nói dối ở đúng chỗ khó thấy nhất — nó vẫn là 100.

Vì sao KHÔNG có tham số `--icc` cho người dùng khai: "'an toàn' phụ thuộc vào
đúng cái mà bạn không biết. Không hằng số mặc định nào an toàn." ICC phải
được ước từ dữ liệu, và khi không đủ dữ liệu để ước thì phải TỪ CHỐI ước chứ
không phải đoán.

Vì sao route do K quyết định chứ không do người khai: ICC ước từ dưới 10
cluster lệch thấp một cách có hệ thống — phạt ít hơn mức cần, tức là lệch về
đúng phía nguy hiểm. Người đang muốn con số đẹp không được phép chọn công
thức tạo ra con số đẹp.

Neo tài liệu: docs/research-notes/01-confidence-intervals.md §1.5, §4.2, §5.B
             docs/design/sdd/01-core-stats.md §4
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from scipy.stats import f as _f_dist

from app.contracts.types import ClusterRoute, Interval
from app.core.stats.intervals import _check_conf, _check_count, interval

#: Ngưỡng chuyển route, theo bảng ở note 01 §4.2.
#: (i)   Đây là chỗ ở duy nhất của hai ngưỡng này trong tầng stats.
#: (ii)  Suy ra từ: note 01 §4.2 (bảng K -> route) và §5.B5 (ICC ước từ <10
#:       cluster lệch thấp có hệ thống).
#: (iii) Xem lại khi: có bằng chứng thực nghiệm mới về độ chệch của ANOVA
#:       estimator ở K nhỏ, hoặc khi tài liệu nền giải quyết được Q6.
K_FOR_ICC = 20
K_FOR_ICC_UPPER = 10


def _validate_clusters(clusters: Sequence[tuple[int, int]]) -> None:
    for idx, item in enumerate(clusters):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError(f"cluster[{idx}] phải là cặp (k, n); nhận {item!r}")
        k, n = item
        _check_count(f"cluster[{idx}].k", k)
        _check_count(f"cluster[{idx}].n", n)
        if n <= 0:
            # Một cluster không có mẫu nào không phải là một cluster. Nếu đếm
            # nó vào K thì K bị thổi lên và route có thể nhảy sai bậc — đúng
            # thứ mà toàn bộ module này sinh ra để chặn.
            raise ValueError(f"cluster[{idx}] có n={n}; cluster rỗng không được tính vào K")
        if k < 0 or k > n:
            raise ValueError(f"cluster[{idx}] có k={k}, n={n}: cần 0 <= k <= n")


def icc_anova(clusters: Sequence[tuple[int, int]]) -> dict[str, Any] | None:
    """Ước ICC bằng ANOVA one-way, TỪ DỮ LIỆU.

    Trả None khi K < 2: với một cluster duy nhất thì "phương sai giữa các
    cluster" không tồn tại — đó là câu hỏi sai chứ không phải dữ liệu hỏng,
    nên không raise. Cũng trả None khi N == K (mỗi cluster đúng 1 mẫu): khi đó
    MSW không còn bậc tự do nào.

    ICC âm (MSB < MSW) bị clamp về 0.0 kèm cờ `clamped`. ICC âm nghĩa là các
    cluster giống nhau HƠN mức ngẫu nhiên; về mặt hiệu chỉnh nó tương đương
    "không có clustering", nhưng cờ phải còn đó — một phép cắt im lặng là thứ
    khiến người đọc tưởng con số ra thẳng từ dữ liệu.
    """
    _validate_clusters(clusters)
    K = len(clusters)
    if K < 2:
        return None

    N = sum(n for _, n in clusters)
    k_total = sum(k for k, _ in clusters)
    if N - K <= 0:
        return None

    p_bar = k_total / N
    msb = sum(n * (k / n - p_bar) ** 2 for k, n in clusters) / (K - 1)
    msw = sum(n * (k / n) * (1 - k / n) for k, n in clusters) / (N - K)
    n0 = (N - sum(n * n for _, n in clusters) / N) / (K - 1)

    degenerate = False
    denom = msb + (n0 - 1) * msw
    if denom <= 0.0:
        # Không có phương sai ở đâu cả (mọi cluster cùng một p̂ thuần 0 hoặc 1).
        # ICC không xác định. Chọn 1.0 — mức phạt tối đa — vì phương sai nội
        # cluster bằng 0 chính là hình dạng của clustering hoàn hảo; đoán 0.0
        # ở đây sẽ là đoán về phía dễ dãi.
        icc_raw = 1.0
        degenerate = True
    else:
        icc_raw = (msb - msw) / denom

    icc = min(1.0, max(0.0, icc_raw))
    clamped = icc != icc_raw

    # Cận trên của ICC. Tài liệu nền chỉ nói "lấy cận trên của nó", không nói
    # bằng phương pháp nào — nên đây là một lựa chọn [DERIVED], không phải một
    # trích dẫn: CI của mô hình one-way random effects qua phân phối F.
    icc_lower_ci: float | None = None
    icc_upper_ci: float = 1.0
    if msw > 0.0 and not degenerate:
        f_obs = msb / msw
        f_u = f_obs * float(_f_dist.ppf(0.975, N - K, K - 1))
        f_l = f_obs / float(_f_dist.ppf(0.975, K - 1, N - K))
        icc_upper_ci = min(1.0, max(0.0, (f_u - 1.0) / (f_u + n0 - 1.0)))
        icc_lower_ci = min(1.0, max(0.0, (f_l - 1.0) / (f_l + n0 - 1.0)))

    warnings: list[str] = []
    if clamped:
        warnings.append(
            f"WARNING: ICC thô = {icc_raw:.6f} nằm ngoài [0,1] và đã bị clamp về {icc:.6f}."
        )
    if degenerate:
        warnings.append(
            "WARNING: không có phương sai trong lẫn ngoài cluster — ICC không xác định. "
            "Đã lấy ICC = 1.0 (phạt tối đa) thay vì đoán về phía dễ dãi."
        )
    if K < K_FOR_ICC_UPPER:
        warnings.append(
            f"WARNING: ICC ước từ K={K} cluster (<{K_FOR_ICC_UPPER}) lệch thấp có hệ thống — "
            f"đừng dùng con số này để hiệu chỉnh, hãy dùng cluster floor."
        )

    return {
        "icc": icc,
        "icc_raw": icc_raw,
        "icc_upper": icc_upper_ci,
        "icc_lower": icc_lower_ci,
        "msb": msb,
        "msw": msw,
        "n0": n0,
        "K": K,
        "N": N,
        "k_total": k_total,
        "p_bar": p_bar,
        "clamped": clamped,
        "degenerate": degenerate,
        "warnings": warnings,
    }


def cluster_adjusted(
    clusters: Sequence[tuple[int, int]],
    conf: float = 0.95,
) -> dict[str, Any]:
    """Interval đã hiệu chỉnh clustering. Route do K quyết định, không do ai khai.

        K >= 20   -> "icc"           ước ICC từ dữ liệu, dùng n_eff
        10..19    -> "icc-upper"     lấy cận trên của ICC, bảo thủ
        K < 10    -> "cluster-floor" mỗi nguồn kể như 1 mẫu, CẤM ước ICC

    Trần cứng `n_eff <= K/ICC` là câu trả lời cho bẫy "thêm sample thay vì
    thêm nguồn": khi m -> vô cùng thì n_eff -> K/ICC. Cùng 100 mẫu, 50 nguồn
    cho n_eff 83.3 còn 2 nguồn chỉ cho 9.3. Mẫu thứ 101 từ nguồn cũ mua thêm
    gần như bằng không.

    Dict trả về LUÔN có `route` và `warnings` dạng câu chữ, vì cả đường đi từ
    đây tới UI phải hiện được một dòng đọc được chứ không phải một icon.
    """
    _check_conf(conf)
    _validate_clusters(clusters)

    K = len(clusters)
    N = sum(n for _, n in clusters)
    k_total = sum(k for k, _ in clusters)
    p_hat = (k_total / N) if N > 0 else 0.0
    warnings: list[str] = []

    stats = icc_anova(clusters)

    if K >= K_FOR_ICC:
        route: ClusterRoute = "icc"
    elif K >= K_FOR_ICC_UPPER:
        route = "icc-upper"
    else:
        route = "cluster-floor"

    if route != "cluster-floor" and stats is None:
        # Đủ cluster về số lượng nhưng không ước được ICC (mỗi cluster 1 mẫu).
        # Rơi về floor, và phải nói rõ là đã rơi.
        warnings.append(
            f"WARNING: K={K} đủ cho route {route} nhưng không ước được ICC "
            f"(N={N} == K, MSW không còn bậc tự do). Đã hạ về cluster-floor."
        )
        route = "cluster-floor"

    icc_used: float | None = None
    ceiling_hit = False

    if route == "cluster-floor":
        # Mỗi nguồn đóng góp đúng một mẫu độc lập. Đây không phải ước lượng
        # bảo thủ của ICC — đây là từ chối ước.
        n_eff = float(K)
        deff = (N / K) if K > 0 else float("inf")
        warnings.append(
            f"WARNING: route=cluster-floor — chỉ K={K} nguồn độc lập "
            f"(<{K_FOR_ICC_UPPER}), CẤM ước ICC; n_eff bị hạ từ N={N} về K={K}. "
            f"Thêm mẫu từ cùng {K} nguồn này KHÔNG cải thiện được con số."
        )
    else:
        assert stats is not None
        icc_used = stats["icc"] if route == "icc" else stats["icc_upper"]
        m_bar = N / K
        deff = 1.0 + (m_bar - 1.0) * icc_used
        n_eff = N / deff if deff > 0 else float(N)
        if icc_used > 0.0:
            ceiling = K / icc_used
            if n_eff > ceiling:
                n_eff = ceiling
                ceiling_hit = True
        n_eff = min(float(N), max(1.0, n_eff))
        if route == "icc-upper":
            warnings.append(
                f"WARNING: route=icc-upper — K={K} nằm trong [{K_FOR_ICC_UPPER},{K_FOR_ICC}), "
                f"dùng CẬN TRÊN của ICC ({icc_used:.4f}) thay vì ước điểm "
                f"({stats['icc']:.4f}). Con số này cố ý bảo thủ."
            )
        if ceiling_hit:
            warnings.append(
                f"WARNING: chạm trần n_eff = K/ICC = {K}/{icc_used:.4f} = {n_eff:.2f}. "
                f"Mẫu thêm từ cùng bộ nguồn này gần như không mua thêm thông tin."
            )
        for w in stats["warnings"]:
            warnings.append(w)

    n_eff_int = max(0, int(round(n_eff)))
    k_eff = min(n_eff_int, max(0, int(round(p_hat * n_eff_int))))
    base = interval(k_eff, n_eff_int, conf=conf, method="wilson")
    adjusted = Interval(
        lower=base.lower,
        upper=base.upper,
        conf=conf,
        method="wilson",
        n=n_eff_int,
        k=k_eff,
        n_eff=n_eff,
        route=route,
        saturated=base.saturated,
    )

    # Interval "ngây thơ" — coi N mẫu là N mẫu độc lập. Giữ lại để báo cáo cho
    # thấy cái giá của việc bỏ qua clustering, không phải để dùng.
    naive = interval(k_total, N, conf=conf, method="wilson")
    width_ratio = (adjusted.width / naive.width) if naive.width > 0 else float("inf")

    if adjusted.saturated:
        warnings.append(
            "WARNING: saturated — interval sau hiệu chỉnh chạm biên. TRÀN, không phải hẹp."
        )
    if width_ratio >= 2.0 and math.isfinite(width_ratio):
        warnings.append(
            f"WARNING: bỏ qua clustering sẽ làm interval hẹp giả {width_ratio:.1f} lần "
            f"({naive.width:.4f} so với {adjusted.width:.4f} thật)."
        )

    return {
        "route": route,
        "cluster_floor": route == "cluster-floor",
        "K": K,
        "N": N,
        "k_total": k_total,
        "p_hat": p_hat,
        "icc": (stats["icc"] if stats else None),
        "icc_upper": (stats["icc_upper"] if stats else None),
        "icc_used": icc_used,
        "deff": deff,
        "n_eff": n_eff,
        "n_eff_int": n_eff_int,
        "k_eff": k_eff,
        "ceiling_hit": ceiling_hit,
        "conf": conf,
        "lower": adjusted.lower,
        "upper": adjusted.upper,
        "width": adjusted.width,
        "saturated": adjusted.saturated,
        "interval": adjusted,
        "naive_lower": naive.lower,
        "naive_upper": naive.upper,
        "naive_width": naive.width,
        "width_ratio": width_ratio,
        "warnings": warnings,
    }
