"""Sàng lọc và hiệu chỉnh LLM judge — vì cái thước cũng có thể cong.

Vì sao module này tồn tại: ba vấn đề chỉ hệ LLM mới có, và nặng nhất là judge
cũng là một LLM. Đo pipeline bằng một thước chưa từng được đo là cách kinh
điển để một con số sai đi qua mọi cổng mà vẫn mang nhãn [OBSERVED].

Vì sao judge_screen phải chạy TRƯỚC judge_adjust: judge có J < 0.5 thì hệ số
khuếch đại lỗi 1/J >= 2, và interval sau hiệu chỉnh nở ra thành [0,1] — vô
thông tin. Với judge như vậy thì việc cần làm là TỪ CHỐI, không phải hiệu
chỉnh. "Judge dưới ~0.75/0.75 -> reject, đừng correct."

Vì sao judge_adjust bắt buộc trả cả giá trị THÔ chưa clamp: đây là bẫy thị
giác nguy hiểm nhất trong cả tài liệu nền. Judge tệ nhất bảng (0.70) cho ra
interval HẸP NHẤT bảng sau clamp (0.1305) trong khi độ rộng thô là 6.68 —
hẹp vì đã tràn rồi bị cắt. Nhìn số đã clamp thì thước tệ nhất trông chắc
chắn nhất. Không có bản thô thì không cách nào phân biệt.

Neo tài liệu: docs/research-notes/01-confidence-intervals.md §1.6, §4.4, §5.C
             docs/design/sdd/01-core-stats.md §5
"""

from __future__ import annotations

import itertools
import math
from typing import Any

from app.core.stats.intervals import _check_conf, _check_count, _check_prob, interval

#: Ngưỡng sàng lọc judge.
#: (i)   Đây là chỗ ở duy nhất của bốn ngưỡng này trong tầng stats; chúng được
#:       phơi ra thành tham số keyword để tầng config bơm vào, không hằng số
#:       nào bị chôn trong thân hàm.
#: (ii)  Suy ra từ: note 01 §4.4 — J >= 0.5 (dưới đó 1/J >= 2, hiệu chỉnh vô
#:       nghĩa); |sens - spec| <= 0.15; n_calib >= 50 tier 1, >= 200 tier 2.
#: (iii) Xem lại khi: có dữ liệu calibration thật của CERTUS đủ để đo lại, hoặc
#:       khi đổi họ model dùng làm judge.
MIN_YOUDEN_J = 0.5
MAX_SENS_SPEC_GAP = 0.15
N_CALIB_TIER1 = 50
N_CALIB_TIER2 = 200


def judge_screen(
    TP: int,
    FN: int,
    TN: int,
    FP: int,
    conf: float = 0.95,
    *,
    min_j: float = MIN_YOUDEN_J,
    max_gap: float = MAX_SENS_SPEC_GAP,
) -> dict[str, Any]:
    """Cổng vào của mọi judge. Trả verdict "ok" | "biased" | "rejected".

    Mẫu số rỗng cho ra "rejected", KHÔNG phải "ok": TP+FN = 0 nghĩa là bộ
    calibration không có một ca positive nào, tức sensitivity CHƯA TỪNG được
    đo. Coi "không đo được" là "đạt" chính là cách một thước chưa bao giờ bị
    kiểm tra đi qua cổng — và đã có ca thật: một chương trình chỉ in ra `0`
    cho mọi trang vẫn được chấm "13/19 đúng" vì dataset không có ca âm.

    Thứ tự kiểm là rejected trước biased: một judge vừa quá yếu vừa lệch thì
    điều cần nói là nó quá yếu.
    """
    _check_conf(conf)
    for name, value in (("TP", TP), ("FN", FN), ("TN", TN), ("FP", FP)):
        _check_count(name, value)
        if value < 0:
            raise ValueError(f"{name} là số đếm không âm; nhận {value}")

    n_pos = TP + FN
    n_neg = TN + FP
    n_calib = n_pos + n_neg
    warnings: list[str] = []

    sens = (TP / n_pos) if n_pos > 0 else None
    spec = (TN / n_neg) if n_neg > 0 else None
    youden_j = (sens + spec - 1.0) if (sens is not None and spec is not None) else None
    error_amplification = (1.0 / youden_j) if (youden_j is not None and youden_j > 0) else None

    sens_iv = interval(TP, n_pos, conf=conf) if n_pos > 0 else None
    spec_iv = interval(TN, n_neg, conf=conf) if n_neg > 0 else None

    if n_pos == 0:
        verdict = "rejected"
        warnings.append(
            "WARNING: judge rejected — bộ calibration không có ca POSITIVE nào (TP+FN=0), "
            "sensitivity chưa từng được đo. Không đo được không phải là đạt."
        )
    elif n_neg == 0:
        verdict = "rejected"
        warnings.append(
            "WARNING: judge rejected — bộ calibration không có ca NEGATIVE nào (TN+FP=0), "
            "specificity chưa từng được đo. Một bộ mẫu không có ca âm không kiểm được thước."
        )
    elif youden_j is None or youden_j < min_j:
        verdict = "rejected"
        amp = f"{error_amplification:.3f}" if error_amplification else "vô cùng"
        warnings.append(
            f"WARNING: judge rejected — Youden J = {youden_j:.4f} < {min_j}, "
            f"khuếch đại lỗi 1/J = {amp}. Kết quả chấm bằng thước này KHÔNG đủ tư cách "
            f"[OBSERVED]; hãy gắn [ASSUMED] và dừng. Sửa thước, đừng hiệu chỉnh nó."
        )
    elif abs(sens - spec) > max_gap:
        verdict = "biased"
        toward = "passing" if sens > spec else "failing"
        warnings.append(
            f"WARNING: judge biased toward {toward} — sens={sens:.4f}, spec={spec:.4f}, "
            f"lệch {abs(sens - spec):.4f} > {max_gap}."
        )
    else:
        verdict = "ok"

    if n_calib < N_CALIB_TIER1:
        tier = 0
        warnings.append(
            f"WARNING: n_calib = {n_calib} < {N_CALIB_TIER1} — chưa đủ cho tier 1. "
            f"Judge chưa calibrate thì kết quả là [ASSUMED: judge uncalibrated] và dừng."
        )
    elif n_calib < N_CALIB_TIER2:
        tier = 1
    else:
        tier = 2

    if verdict == "ok" and tier >= 1:
        warnings.append(
            "NOTE: judge đạt cổng, nhưng lỗi của judge vẫn CHƯA được hiệu chỉnh khỏi "
            "con số cuối — ghi chú điều đó cạnh nhãn [OBSERVED]."
        )

    return {
        "TP": TP,
        "FN": FN,
        "TN": TN,
        "FP": FP,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "n_calib": n_calib,
        "sens": sens,
        "spec": spec,
        "youden_j": youden_j,
        "error_amplification": error_amplification,
        "verdict": verdict,
        "tier": tier,
        "conf": conf,
        "sens_interval": ([sens_iv.lower, sens_iv.upper] if sens_iv else None),
        "spec_interval": ([spec_iv.lower, spec_iv.upper] if spec_iv else None),
        "warnings": warnings,
    }


def rogan_gladen(p_obs: float, sens: float, spec: float) -> float | None:
    """Gỡ lỗi judge khỏi tỉ lệ quan sát được.

        p_true = (p_obs + spec - 1) / (sens + spec - 1)

    Trả None khi sens + spec <= 1: thước đó không hơn tung đồng xu, phép đảo
    đơn giản là không tồn tại. Trả một con số ở đó sẽ là bịa.

    CỐ Ý KHÔNG clamp về [0,1]. Giá trị 1.0259 không phải một con số cần cắt
    gọn — nó là tín hiệu báo động rằng mô hình judge không khớp dữ liệu. Người
    gọi mới là chỗ được clamp, và chỗ đó phải giữ lại bản thô.
    """
    _check_prob("p_obs", p_obs)
    _check_prob("sens", sens)
    _check_prob("spec", spec)
    youden_j = sens + spec - 1.0
    if youden_j <= 0.0:
        return None
    return (p_obs + spec - 1.0) / youden_j


def judge_adjust(
    k: int,
    n: int,
    TP: int,
    FN: int,
    TN: int,
    FP: int,
    conf: float = 0.95,
    split: int = 3,
) -> dict[str, Any]:
    """Interval của tỉ lệ THẬT, sau khi gỡ lỗi của judge — hoặc lời từ chối.

    Ba nguồn bất định độc lập: p_obs, sens, spec. Chia alpha làm `split` phần
    (Bonferroni), lấy interval cho từng cái, rồi lấy bao của 8 GÓC hộp qua
    Rogan-Gladen. Bao 8 góc là đủ vì Rogan-Gladen đơn điệu theo từng biến
    trong miền J > 0.

    J <= 0 hoặc judge bị rejected thì trả thẳng [0,1] và KHÔNG chia 0. Đây là
    ca đã đo được: J = 0.4650 -> 1/J = 2.15 -> interval hợp nhất [0.0000,
    1.0000]. Một kết quả vô thông tin phải TRÔNG vô thông tin.

    `raw_lower` / `raw_upper` là giá trị CHƯA clamp; `None` nghĩa là vô cực,
    tức tràn hẳn (JSON không biểu diễn được Infinity). Chúng tồn tại vì độ
    rộng sau clamp là một con số biết nói dối: judge càng tệ, interval sau
    clamp trông càng hẹp.
    """
    _check_conf(conf)
    if not isinstance(split, int) or isinstance(split, bool) or split < 1:
        raise ValueError(f"split phải là số nguyên >= 1; nhận {split!r}")

    screen = judge_screen(TP, FN, TN, FP, conf=conf)
    warnings: list[str] = list(screen["warnings"])

    # Bonferroni: mỗi thành phần gánh alpha/split để tổng sai lầm vẫn <= alpha.
    conf_each = 1.0 - (1.0 - conf) / split
    obs = interval(k, n, conf=conf_each, method="wilson")

    if screen["verdict"] == "rejected" or screen["youden_j"] is None or screen["youden_j"] <= 0.0:
        warnings.append(
            "WARNING: không hiệu chỉnh — thước không đạt cổng, nên interval hợp nhất là "
            "[0,1]: vô thông tin. Đây là kết quả đúng, không phải lỗi tính toán."
        )
        return {
            "k": k,
            "n": n,
            "p_hat": (k / n) if n > 0 else None,
            "conf": conf,
            "split": split,
            "conf_each": conf_each,
            "verdict": "rejected",
            "sens": screen["sens"],
            "spec": screen["spec"],
            "youden_j": screen["youden_j"],
            "error_amplification": screen["error_amplification"],
            "obs_interval": [obs.lower, obs.upper],
            "sens_interval": screen["sens_interval"],
            "spec_interval": screen["spec_interval"],
            "point_raw": None,
            "raw_lower": None,
            "raw_upper": None,
            "raw_width": None,
            "lower": 0.0,
            "upper": 1.0,
            "width": 1.0,
            "saturated_low": True,
            "saturated_high": True,
            "saturated": True,
            "screen": screen,
            "warnings": warnings,
        }

    sens_iv = interval(TP, TP + FN, conf=conf_each, method="wilson")
    spec_iv = interval(TN, TN + FP, conf=conf_each, method="wilson")

    corners: list[float] = []
    unbounded = False
    for p_c, s_c, sp_c in itertools.product(
        (obs.lower, obs.upper), (sens_iv.lower, sens_iv.upper), (spec_iv.lower, spec_iv.upper)
    ):
        value = rogan_gladen(p_c, s_c, sp_c)
        if value is None:
            # Một góc của hộp có J <= 0: ở đó phép đảo phân kỳ, nên bao của
            # toàn hộp là vô hạn cả hai phía. Thu nhỏ nó lại sẽ là bịa ra độ
            # chắc chắn không có.
            unbounded = True
            break
        corners.append(value)

    if unbounded:
        raw_lower: float | None = None
        raw_upper: float | None = None
        lower, upper = 0.0, 1.0
        saturated_low = saturated_high = True
        warnings.append(
            "WARNING: interval của sens/spec chạm vùng J <= 0 — bao hiệu chỉnh phân kỳ. "
            "Kết quả là [0,1]: thước chưa đủ chắc để gỡ lỗi cho bất kỳ con số nào."
        )
    else:
        raw_lower = min(corners)
        raw_upper = max(corners)
        lower = max(0.0, raw_lower)
        upper = min(1.0, raw_upper)
        saturated_low = raw_lower < 0.0
        saturated_high = raw_upper > 1.0

    point_raw = rogan_gladen(
        (k / n) if n > 0 else 0.0, screen["sens"], screen["spec"]
    ) if n > 0 else None

    if point_raw is not None and not (0.0 <= point_raw <= 1.0):
        warnings.append(
            f"WARNING: ước điểm sau hiệu chỉnh = {point_raw:.4f} nằm NGOÀI [0,1]. "
            f"Đây là tín hiệu mô hình judge không khớp dữ liệu, không phải con số để cắt gọn."
        )
    if saturated_low or saturated_high:
        raw_txt = (
            f"{raw_upper - raw_lower:.4f}"
            if (raw_lower is not None and raw_upper is not None)
            else "vô hạn"
        )
        warnings.append(
            f"WARNING: saturated — interval đã TRÀN ra ngoài [0,1] rồi bị cắt về "
            f"[{lower:.4f}, {upper:.4f}]. Độ rộng thô là {raw_txt}; đừng đọc nó là 'hẹp'."
        )

    raw_width = (
        (raw_upper - raw_lower) if (raw_lower is not None and raw_upper is not None) else None
    )

    return {
        "k": k,
        "n": n,
        "p_hat": (k / n) if n > 0 else None,
        "conf": conf,
        "split": split,
        "conf_each": conf_each,
        "verdict": screen["verdict"],
        "sens": screen["sens"],
        "spec": screen["spec"],
        "youden_j": screen["youden_j"],
        "error_amplification": screen["error_amplification"],
        "obs_interval": [obs.lower, obs.upper],
        "sens_interval": [sens_iv.lower, sens_iv.upper],
        "spec_interval": [spec_iv.lower, spec_iv.upper],
        "point_raw": point_raw,
        "raw_lower": raw_lower,
        "raw_upper": raw_upper,
        "raw_width": raw_width,
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
        "saturated_low": saturated_low,
        "saturated_high": saturated_high,
        "saturated": saturated_low or saturated_high or math.isclose(upper - lower, 1.0),
        "screen": screen,
        "warnings": warnings,
    }
