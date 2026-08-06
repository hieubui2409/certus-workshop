"""Khoảng tin cậy cho tỉ lệ — thước đo của toàn bộ CERTUS.

Vì sao module này tồn tại: bước từ "8/10" sang "80% accuracy" cảm giác hiển
nhiên tới mức không ai coi nó là một bước. Nó là một bước, và nó không có cơ
sở nào. Sự thật của 8/10 là [0.4902, 0.9433].

Vì sao gần như không có công thức nào tự viết ở đây: scipy và statsmodels đã
có bản chín của Wilson, Clopper-Pearson, Jeffreys, McNemar và regularized
incomplete beta. Tài liệu nền ghi lại một bug có thật khi tự cài Beta tail
thuần Python (exp(logB) underflow về 0 khi a+b >= 500 → ZeroDivisionError);
gọi `scipy.stats.beta.sf` làm bug đó không thể tái xuất hiện.

Vì sao mọi hàm ở đây đều trả cờ chứ không chỉ trả số: rủi ro lớn nhất của cả
phương pháp là cargo cult — người ta dán một interval vào báo cáo, thấy một
con số trông khoa học, và không bao giờ đọc phần cảnh báo. Phòng thủ duy nhất
là công cụ phải LÊN TIẾNG. "A silent number is easy to ignore. A line reading
`WARNING: judge biased toward passing` is not."

Neo tài liệu: docs/research-notes/01-confidence-intervals.md §1, §4, §6
             docs/design/sdd/01-core-stats.md §3
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from statistics import NormalDist
from typing import Any, get_args

from scipy.stats import beta as _beta_dist
from scipy.stats import binom as _binom_dist
from scipy.stats import binomtest
from statsmodels.stats.contingency_tables import mcnemar as _sm_mcnemar
from statsmodels.stats.proportion import proportion_confint

from app.contracts.types import Interval, IntervalMethod

#: Đúng bốn method có trong tài liệu nền. Agresti-Coull cố ý KHÔNG có mặt dù
#: statsmodels cài sẵn: nó không xuất hiện lần nào trong tài liệu gốc, và
#: `contracts.types.IntervalMethod` là Literal đã khoá — thêm cái thứ năm ở
#: đây sẽ làm hai nửa hệ thống nói hai thứ tiếng khác nhau.
METHODS: tuple[str, ...] = get_args(IntervalMethod)

#: Trần quét của `min_n_all_pass`. Không phải ngưỡng chính sách, chỉ là hàng
#: rào chống treo vòng lặp — vượt qua nó thì raise chứ không trả None im lặng.
_MAX_SCAN_N = 100_000


# ───────────────────────────── kiểm tra đầu vào ─────────────────────────────


def _check_count(name: str, value: Any) -> None:
    """k và n là SỐ ĐẾM, không phải tỉ lệ.

    `interval(0.8, 10)` là lỗi khái niệm chứ không phải lỗi kiểu: người gọi
    đang đưa một tỉ lệ vào chỗ dành cho số đếm — tức là đã đánh mất chính cái
    n mà module này sinh ra để bảo vệ. Ép kiểu im lặng sẽ nuốt mất cái sai đó.
    `bool` là subclass của `int` trong Python nên phải loại riêng, nếu không
    `interval(True, True)` sẽ chạy ngon lành.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} phải là int (số đếm), nhận {type(value).__name__}: {value!r}")


def _check_kn(k: int, n: int) -> None:
    _check_count("k", k)
    _check_count("n", n)
    if n < 0:
        raise ValueError(f"n âm: {n}")
    if k < 0:
        raise ValueError(f"k âm: {k}")
    if k > n:
        raise ValueError(f"k > n: {k}/{n} — số thành công không thể nhiều hơn số lần thử")


def _check_conf(conf: float) -> None:
    """Chặn cả `conf=95` (nhầm phần trăm) lẫn `conf=1.0` (đòi chắc chắn tuyệt
    đối, thứ không một mẫu hữu hạn nào mua được)."""
    if not isinstance(conf, (int, float)) or isinstance(conf, bool):
        raise TypeError(f"conf phải là số thực, nhận {type(conf).__name__}")
    if math.isnan(conf) or not (0.0 < conf < 1.0):
        raise ValueError(f"conf phải nằm trong khoảng mở (0,1), nhận {conf!r}")


def _check_method(method: str) -> None:
    if method not in METHODS:
        raise ValueError(f"method không hợp lệ: {method!r}; chọn một trong {list(METHODS)}")


def _check_prob(name: str, p: float) -> None:
    if not isinstance(p, (int, float)) or isinstance(p, bool):
        raise TypeError(f"{name} phải là số thực, nhận {type(p).__name__}")
    if math.isnan(p) or not (0.0 <= p <= 1.0):
        raise ValueError(f"{name} phải nằm trong [0,1], nhận {p!r}")


# ───────────────────────────────── z-score ──────────────────────────────────


def z_for(conf: float) -> float:
    """z hai phía — luôn TÍNH, không bao giờ tra bảng thuộc lòng.

    Bẫy đã có tiền lệ: 2.33 là z MỘT phía của 99%, hai phía là 2.5758. Dùng
    nhầm cho ra interval hẹp giả mà không có dấu hiệu nào trên bề mặt.
    """
    _check_conf(conf)
    return NormalDist().inv_cdf(1.0 - (1.0 - conf) / 2.0)


# ──────────────────────────────── interval ──────────────────────────────────


def _raw_bounds(k: int, n: int, conf: float, method: str) -> tuple[float, float]:
    """Gọi thư viện. Đây là toàn bộ phần "công thức" của module này.

    scipy phủ ba method dựa trên tần suất; statsmodels phủ Jeffreys (Bayesian).
    Không có nhánh nào tự nhân z với căn bậc hai ở đây — đó là chủ ý.
    """
    if method == "wilson":
        ci = binomtest(k, n).proportion_ci(confidence_level=conf, method="wilson")
    elif method == "wilson-cc":
        ci = binomtest(k, n).proportion_ci(confidence_level=conf, method="wilsoncc")
    elif method == "clopper-pearson":
        ci = binomtest(k, n).proportion_ci(confidence_level=conf, method="exact")
    else:  # jeffreys
        lo, hi = proportion_confint(k, n, alpha=1.0 - conf, method="jeffreys")
        return float(lo), float(hi)
    return float(ci.low), float(ci.high)


def interval(
    k: int,
    n: int,
    conf: float = 0.95,
    method: IntervalMethod = "wilson",
) -> Interval:
    """Khoảng tin cậy cho k/n.

    `n == 0` trả [0,1] và KHÔNG raise: "chưa đo gì" là một câu trả lời hợp lệ
    và đây là cách phát biểu nó cho đúng. Chia 0 thì không hợp lệ, nên nhánh
    này phải nằm trước mọi phép tính.

    Cờ `saturated` nghĩa là interval đã CHẠM biên — tức là nó đã tràn ra ngoài
    [0,1] rồi bị cắt về, KHÔNG phải là nó hẹp vì có nhiều dữ liệu. Đây là chỗ
    trực giác phản bội mạnh nhất: một thước đo tệ cho ra interval trông chắc
    chắn nhất bảng đúng vì lý do này.
    """
    _check_conf(conf)
    _check_method(method)
    _check_kn(k, n)

    if n == 0:
        # Không có mẫu số thì mọi tỉ lệ đều còn khả dĩ. Cờ saturated bật vì
        # khoảng này chạm cả hai biên — đọc nó như "hẹp" là đọc ngược.
        return Interval(lower=0.0, upper=1.0, conf=conf, method=method, n=0, k=0, saturated=True)

    lower, upper = _raw_bounds(k, n, conf, method)

    # Ép cứng hai biên. Đúng về toán cho cả bốn method (k=0 thì cận dưới là 0,
    # k=n thì cận trên là 1), và nó tồn tại để biên so sánh được bằng `==`
    # thay vì bằng dung sai — biên là chỗ hay sai nhất nên phải chặt nhất.
    if k == 0:
        lower = 0.0
    if k == n:
        upper = 1.0
    lower = max(0.0, min(1.0, lower))
    upper = max(0.0, min(1.0, upper))

    return Interval(
        lower=lower,
        upper=upper,
        conf=conf,
        method=method,
        n=n,
        k=k,
        saturated=(lower == 0.0 or upper == 1.0),
    )


def interval_full(
    k: int,
    n: int,
    conf: float = 0.95,
    method: IntervalMethod = "wilson",
) -> dict[str, Any]:
    """Bản đầy đủ, để báo cáo và để dạy.

    `center` được trả ra riêng vì nó KHÔNG bằng p̂ — đó là bài học trung tâm
    của Wilson: 10/10 cho p̂ = 1.00 nhưng center = 0.8612. Ai chỉ nhìn p̂ sẽ
    không bao giờ thấy Wilson đã kéo con số về đâu.
    """
    iv = interval(k, n, conf=conf, method=method)
    p_hat = (k / n) if n > 0 else float("nan")
    center = (iv.lower + iv.upper) / 2.0
    half_width = (iv.upper - iv.lower) / 2.0

    warnings: list[str] = []
    if n == 0:
        warnings.append("WARNING: n=0 — chưa đo gì. [0,1] là ABSTAIN, không phải kết quả.")
    elif iv.saturated:
        touched = [name for name, hit in (("0.0", iv.lower == 0.0), ("1.0", iv.upper == 1.0)) if hit]
        warnings.append(
            f"WARNING: saturated — interval chạm biên ({' và '.join(touched)}). "
            f"Đây là TRÀN, không phải hẹp."
        )

    return {
        "k": k,
        "n": n,
        "p_hat": p_hat,
        "z": z_for(conf),
        "center": center,
        "half_width": half_width,
        "lower": iv.lower,
        "upper": iv.upper,
        "width": iv.width,
        "conf": conf,
        "method": method,
        "saturated": iv.saturated,
        "warnings": warnings,
    }


# ───────────────────────────── bảng quyết định ──────────────────────────────


def min_n_all_pass(
    target: float,
    conf: float = 0.95,
    method: IntervalMethod = "wilson",
) -> int:
    """n nhỏ nhất để một lượt chạy TOÀN PASS (k=n) đảm bảo lower >= target.

    Đây là bảng dán tường quan trọng nhất của cả phương pháp, vì nó trả lời
    câu hỏi người ta thực sự hỏi: "cần bao nhiêu mẫu?". T=0.95 cần 73 mẫu
    toàn pass với Wilson — nên một golden set 30 mẫu KHÔNG BAO GIỜ chứng minh
    được >= 90%, dù có sạch tuyệt đối.
    """
    _check_conf(conf)
    _check_method(method)
    _check_prob("target", target)
    if target >= 1.0:
        raise ValueError("target = 1.0 là bất khả với mọi n hữu hạn — không mẫu nào mua được sự chắc chắn tuyệt đối")

    for n in range(1, _MAX_SCAN_N + 1):
        if interval(n, n, conf=conf, method=method).lower >= target:
            return n
    raise ValueError(
        f"không đạt target={target} với method={method}, conf={conf} trong {_MAX_SCAN_N} mẫu"
    )


def max_fails(
    n: int,
    target: float,
    conf: float = 0.95,
    method: IntervalMethod = "wilson",
) -> int | None:
    """Số fail tối đa còn giữ được lower >= target, hoặc None nếu BẤT KHẢ.

    `None` ở đây có nghĩa rất cụ thể: "kể cả n/n cũng không đạt". Đó là ca
    n=30 với T=0.90. Trả 0 cho ca đó sẽ là nói dối theo đúng hướng nguy hiểm —
    người đọc sẽ tưởng "chạy sạch là qua".
    """
    _check_conf(conf)
    _check_method(method)
    _check_kn(0, n)
    _check_prob("target", target)

    if n == 0 or interval(n, n, conf=conf, method=method).lower < target:
        return None
    for f in range(0, n + 1):
        if interval(n - f, n, conf=conf, method=method).lower < target:
            return f - 1
    return n


def coverage(
    n: int,
    p: float,
    conf: float = 0.95,
    method: IntervalMethod = "wilson",
) -> float:
    """Coverage THẬT: tổng chính xác trên k=0..n, không simulation.

    Con số này tồn tại để phản bác niềm tin "Wilson95 nghĩa là đúng 95%".
    Coverage thật ở n=10, p=0.30 là 0.9244. Quét p cho thấy 40-58% giá trị p
    có coverage dưới 0.95, tệ nhất 0.9044 — và n lớn hơn KHÔNG cứu được.
    Hãy đọc "Wilson95" là "khoảng 92-95%".

    Không dùng Monte Carlo: một con số dùng để phản bác mà tự nó có nhiễu thì
    phản bác không đứng vững.
    """
    _check_conf(conf)
    _check_method(method)
    _check_count("n", n)
    if n < 0:
        raise ValueError(f"n âm: {n}")
    _check_prob("p", p)

    total = 0.0
    for k in range(0, n + 1):
        iv = interval(k, n, conf=conf, method=method)
        if iv.lower <= p <= iv.upper:
            total += float(_binom_dist.pmf(k, n, p))
    return total


# ─────────────────────────── so sánh hai candidate ──────────────────────────
#
# Cố ý KHÔNG có hàm nào tên kiểu `intervals_overlap()`. Đọc hai interval chồng
# nhau rồi kết luận "không phân biệt được" là một LỖI ĐỌC: mỗi interval đã tự
# trả giá cho phần bất định của riêng nó, xét theo độ chồng là đếm phần bất
# định đó hai lần. Hậu quả là bỏ lỡ cải tiến thật — 90/100 so 80/100 có hai
# interval chồng nhau nhưng difference interval là [+0.0001, +0.1995].


def mcnemar_wilson(b: int, c: int, conf: float = 0.95) -> dict[str, Any]:
    """So hai candidate trên CÙNG test set.

    b = A đúng B sai, c = A sai B đúng. Các ca cả hai cùng đúng hoặc cùng sai
    không mang thông tin phân biệt nên không vào mẫu số — dùng hai interval
    độc lập ở đây sẽ vứt bỏ phần lớn power.

    `conclusive` khi interval của b/(b+c) KHÔNG chứa 0.5.
    """
    _check_conf(conf)
    _check_count("b", b)
    _check_count("c", c)
    if b < 0 or c < 0:
        raise ValueError(f"b, c là số đếm không âm; nhận b={b}, c={c}")

    n_disc = b + c
    warnings: list[str] = []

    if n_disc == 0:
        # Không một ca nào hai candidate khác nhau. Đó KHÔNG phải bằng chứng
        # chúng bằng nhau — đó là chưa có bằng chứng nào cả.
        warnings.append(
            "WARNING: n_disc=0 — hai candidate không khác nhau ở ca nào. "
            "Đây là 'chưa đo được', không phải 'bằng nhau'."
        )
        return {
            "b": b,
            "c": c,
            "n_disc": 0,
            "p_hat": None,
            "lower": 0.0,
            "upper": 1.0,
            "conf": conf,
            "conclusive": False,
            "direction": None,
            "p_value": 1.0,
            "warnings": warnings,
        }

    iv = interval(b, n_disc, conf=conf, method="wilson")
    conclusive = not (iv.lower <= 0.5 <= iv.upper)
    direction = None
    if conclusive:
        direction = "A" if iv.lower > 0.5 else "B"

    result = _sm_mcnemar([[0, b], [c, 0]], exact=True)
    p_value = float(result.pvalue)

    if not conclusive:
        warnings.append(
            f"WARNING: không kết luận được — interval [{iv.lower:.4f}, {iv.upper:.4f}] "
            f"chứa 0.5 trên n_disc={n_disc} ca phân biệt. Interval rộng nghĩa là "
            f"'chạy thêm mẫu', không phải 'dừng'."
        )
    if iv.saturated:
        warnings.append("WARNING: saturated — interval chạm biên, đây là TRÀN chứ không phải hẹp.")

    return {
        "b": b,
        "c": c,
        "n_disc": n_disc,
        "p_hat": b / n_disc,
        "lower": iv.lower,
        "upper": iv.upper,
        "conf": conf,
        "conclusive": conclusive,
        "direction": direction,
        "p_value": p_value,
        "warnings": warnings,
    }


def diff_newcombe(
    k1: int,
    n1: int,
    k2: int,
    n2: int,
    conf: float = 0.95,
) -> dict[str, Any]:
    """Difference interval (Newcombe) — so hai candidate trên test set KHÁC nhau.

    Đây là câu trả lời cho lỗi đọc "hai interval chồng nhau nên không kết luận
    được". Với 90/100 so 80/100, hai interval Wilson chồng nhau rõ rệt, nhưng
    difference interval là [+0.0001, +0.1995] — kết luận được, và kết luận đó
    là một cải tiến thật suýt bị vứt đi.
    """
    _check_conf(conf)
    iv1 = interval(k1, n1, conf=conf, method="wilson")
    iv2 = interval(k2, n2, conf=conf, method="wilson")
    if n1 == 0 or n2 == 0:
        raise ValueError("diff_newcombe cần cả hai n > 0; n=0 thì không có gì để so")

    p1, p2 = k1 / n1, k2 / n2
    delta = p1 - p2
    lower = delta - math.sqrt((p1 - iv1.lower) ** 2 + (iv2.upper - p2) ** 2)
    upper = delta + math.sqrt((iv1.upper - p1) ** 2 + (p2 - iv2.lower) ** 2)
    lower = max(-1.0, lower)
    upper = min(1.0, upper)

    conclusive = not (lower <= 0.0 <= upper)
    warnings: list[str] = []
    if not conclusive:
        warnings.append(
            f"WARNING: không kết luận được — difference interval "
            f"[{lower:.4f}, {upper:.4f}] chứa 0."
        )
    if lower <= -1.0 or upper >= 1.0:
        warnings.append("WARNING: saturated — difference interval chạm biên +-1.")

    return {
        "k1": k1,
        "n1": n1,
        "k2": k2,
        "n2": n2,
        "p1": p1,
        "p2": p2,
        "diff": delta,
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
        "conf": conf,
        "conclusive": conclusive,
        "direction": (None if not conclusive else ("A" if lower > 0.0 else "B")),
        "interval_1": [iv1.lower, iv1.upper],
        "interval_2": [iv2.lower, iv2.upper],
        "saturated": lower <= -1.0 or upper >= 1.0,
        "warnings": warnings,
    }


# ──────────────────────────────── Bayesian ──────────────────────────────────


def posterior_prob_ge(
    k: int,
    n: int,
    T: float,
    prior_a: float = 0.5,
    prior_b: float = 0.5,
) -> float:
    """P(p >= T | data) với posterior Beta(k+a, n-k+b).

    Vì sao cần con số này bên cạnh Wilson lower: chúng trả lời hai câu hỏi
    khác nhau và CÓ THỂ bất đồng. Với 30/30 và T=0.90: Wilson lower 0.8865
    (FAIL) nhưng P(p>=0.90) = 0.9884 (PASS). Ship đồ tệ rất đắt thì đọc Wilson
    lower; chặn đồ tốt cũng đắt thì đọc P(p>=T); không rõ thì in cả hai và để
    người quyết.

    Cài đặt gọi `scipy.stats.beta.sf` — hàm beta không đầy đủ đã chuẩn hoá,
    cài trong log space. Bản tự viết thuần Python từng chia sau bằng
    `integral / exp(logB)` và underflow về 0 khi a+b >= 500, cho ZeroDivisionError.
    Test cho a+b >= 500 vẫn phải giữ: bỏ nó đi thì lần sau ai đó thay scipy
    bằng tay sẽ dựng lại đúng bug đó mà không ai thấy.
    """
    _check_kn(k, n)
    _check_prob("T", T)
    if prior_a <= 0 or prior_b <= 0:
        raise ValueError(f"prior_a, prior_b phải dương; nhận ({prior_a}, {prior_b})")
    return float(_beta_dist.sf(T, k + prior_a, n - k + prior_b))


def prior_from_evidence(k_old: int, n_old: int, weight: float) -> tuple[float, float]:
    """Biến bằng chứng cũ thành prior Beta(a, b), có chiết khấu.

    RAISE khi weight > 0.5, và đây là hàng rào cứng chứ không phải tuỳ chọn.
    Đã đo được: với sự thật 0.60 và một prior sai "450/500 = 0.90", kể cả 3000
    sample mới vẫn chưa kéo posterior về sự thật. Prior nặng không phải là
    "dùng kinh nghiệm", nó là ghi đè dữ liệu bằng niềm tin.

    Không có giá trị mặc định cho `weight`: bảng trọng số prior là một phán
    đoán chủ quan, chưa dẫn được từ dữ liệu — nó đang đứng đúng vị trí mà
    "ICC mặc định = 0.3" từng đứng trước khi bị bác bỏ. Người gọi phải khai,
    và phải cite nguồn của k_old/n_old.
    """
    _check_kn(k_old, n_old)
    if not isinstance(weight, (int, float)) or isinstance(weight, bool):
        raise TypeError(f"weight phải là số thực, nhận {type(weight).__name__}")
    if math.isnan(weight) or weight <= 0.0:
        raise ValueError(f"weight phải dương; nhận {weight!r}")
    if weight > 0.5:
        raise ValueError(
            f"weight={weight} vượt trần 0.5. Bằng chứng cũ không được nặng hơn một nửa "
            f"bằng chứng mới: một prior sai với w lớn thì hàng nghìn sample cũng không sửa nổi."
        )
    return (0.5 + weight * k_old, 0.5 + weight * (n_old - k_old))


# ─────────────────────────────────── CLI ────────────────────────────────────

_EXIT_OK = 0
_EXIT_BELOW_THRESHOLD = 1
_EXIT_INVALID_INPUT = 2


def _render_human(full: dict[str, Any], threshold: float | None) -> str:
    """Bản người đọc. Cờ phải hiện thành CÂU, không phải ký hiệu — một dòng
    chữ khó lờ đi hơn một icon rất nhiều."""
    lines: list[str] = []
    p_hat = full["p_hat"]
    p_txt = "n/a" if math.isnan(p_hat) else f"{p_hat:.6f}"
    lines.append(f"  {full['k']}/{full['n']}   p_hat = {p_txt}")
    lines.append(
        f"  {full['method']} {full['conf'] * 100:g}%  "
        f"[{full['lower']:.6f}, {full['upper']:.6f}]   width {full['width']:.6f}"
    )
    lines.append(f"  center = {full['center']:.6f}   z = {full['z']:.6f}")
    for w in full["warnings"]:
        lines.append(f"  {w}")
    if threshold is not None:
        verdict = "PASS" if full["lower"] >= threshold else "FAIL"
        lines.append(
            f"  threshold {threshold:.6f} vs lower bound {full['lower']:.6f}  ->  {verdict}"
        )
        lines.append("  (số dùng để QUYẾT ĐỊNH là cận dưới: nó trả lời 'trường hợp tệ nhất tệ tới đâu')")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.core.stats.intervals",
        description="Khoảng tin cậy cho k/n — in kèm cờ cảnh báo, không chỉ in số.",
    )
    parser.add_argument("--k", type=int, required=True, help="số lần thành công")
    parser.add_argument("--n", type=int, required=True, help="số ITEM ĐỘC LẬP, không phải số dòng log")
    parser.add_argument("--conf", type=float, default=0.95)
    parser.add_argument("--method", choices=list(METHODS), default="wilson")
    parser.add_argument("--threshold", type=float, default=None, help="ngưỡng so với CẬN DƯỚI")
    parser.add_argument("--json", action="store_true", help="in JSON, KHÔNG làm tròn")
    args = parser.parse_args(argv)

    try:
        full = interval_full(args.k, args.n, conf=args.conf, method=args.method)
    except (ValueError, TypeError) as exc:
        print(f"input không hợp lệ: {exc}", file=sys.stderr)
        return _EXIT_INVALID_INPUT

    if args.json:
        # Không làm tròn: số dành cho máy đọc mà mất chữ số thì downstream
        # không tái lập được kết quả.
        print(json.dumps(full, ensure_ascii=False, allow_nan=True))
    else:
        print(_render_human(full, args.threshold))

    if args.threshold is not None and full["lower"] < args.threshold:
        return _EXIT_BELOW_THRESHOLD
    return _EXIT_OK


if __name__ == "__main__":  # pragma: no cover - lối vào CLI
    raise SystemExit(main())
