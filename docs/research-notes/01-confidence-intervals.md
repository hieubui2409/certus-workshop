# Research note 01 — Confidence intervals for probe-first

**Nguồn chính:** `/home/hieubt15/Documents/vsf/sdlc-harness/docs/research/methodology/confidence-intervals/confidence-intervals-for-probe-first_en.md` (3113 dòng)
**Nguồn bổ sung:** `harness/rules/verification-mechanism.md` (canonical home của hệ 4 nhãn), `harness/rules/harness-contract.md` (định nghĩa probe-first)

> ⚠️ **Cảnh báo nguồn.** File confidence-intervals **chỉ nhắc 3 nhãn** (`OBSERVED`, `ASSUMED`, `PRIOR`) ở dòng 359–361. **`[DERIVED]` không xuất hiện lần nào** (grep: 0 hit). Muốn cite hệ 4 nhãn thì phải cite `verification-mechanism.md:23–50`. Nhầm nguồn ở đây chính là một ca `[PRIOR]` bị gắn nhãn `[OBSERVED]` — đúng thứ workshop đi dạy.

---

## 1. Công thức — code-ready

### 1.1 z-score: TÍNH, không tra bảng

```
alpha = 1 − conf
z     = Φ⁻¹(1 − alpha/2)     # statistics.NormalDist().inv_cdf(1 - alpha/2)

conf 0.90 → z = 1.644854
conf 0.95 → z = 1.959964
conf 0.99 → z = 2.575829
```

Bẫy (dòng 545–548): `2.33` là z **one-tailed** 99%. Dùng nhầm → interval hẹp giả.

### 1.2 Wilson score interval (dòng 552–560) — công thức trung tâm

```
denominator = 1 + z²/n
center      = ( p̂ + z²/(2n) ) / denominator
half_width  = ( z / denominator ) · √( p̂(1−p̂)/n + z²/(4n²) )
CI          = [center − half_width, center + half_width]
```

```python
from statistics import NormalDist
import math

def wilson(k, n, conf=0.95):
    if n == 0:
        return (0.0, 1.0)          # không raise, không chia 0
    z = NormalDist().inv_cdf(1 - (1 - conf) / 2)
    p = k / n
    denom  = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half   = (z / denom) * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return (max(0.0, center - half), min(1.0, center + half))
```

Ba điều phải hiểu để dạy được:

- **`center ≠ p̂`.** Numerator cộng `z²/(2n)` ≈ `1.92/n` ở 95% → kéo center về 0.5. `10/10 → p̂=1.00 nhưng center=0.8612`; `100/100 → center=0.9815`.
- **Trong căn có HAI số hạng.** `p̂(1−p̂)/n` là variance thường, chết bằng 0 khi p̂ = 0 hoặc 1. `z²/(4n²)` là **lifesaver term** — luôn dương, giữ interval không sụp. Kiểm chứng k=10, n=10: số hạng đầu = 0.000000, số hạng sau = 0.009604, half = 0.138766.
- **`denominator → 1` khi n lớn** → Wilson hội tụ về Wald. Khác biệt **chỉ tồn tại ở vùng small-data** — tức đúng vùng probe-first sống.

Trực giác dạy học (dòng 486–491): Wilson ≈ **thêm 2 phantom trial** — 1 success, 1 failure.

### 1.3 Wald — công thức phản ví dụ (dòng 459–473)

```
p̂ ± z·√( p̂(1−p̂)/n )
```

| Quan sát | Wald 95% | Wilson 95% |
|---|---|---|
| 8/10 | [0.5521, **1.0479**] | [0.4902, 0.9433] |
| 2/3 | [0.1332, **1.2001**] | [0.2077, 0.9385] |
| 1/20 | [**−0.0455**, 0.1455] | [0.0089, 0.2361] |
| 10/10 | [**1.0000, 1.0000**] | [0.7225, 1.0000] |
| 0/30 | [**0.0000, 0.0000**] | [0.0000, 0.1135] |

Nguy hiểm nhất: *"'Certainly 100%, zero error' appears right after a clean probe — when your guard is lowest."*

### 1.4 Các method khác

**Wilson-CC (continuity correction, Newcombe 1998)** — dòng 927–933:
```
lower = [ 2np̂ + z² − 1 − z·√( z² − 2 − 1/n + 4p̂(n(1−p̂) + 1) ) ] / [ 2(n + z²) ]
upper = [ 2np̂ + z² + 1 + z·√( z² + 2 − 1/n + 4p̂(n(1−p̂) − 1) ) ] / [ 2(n + z²) ]
k = 0 → lower đúng bằng 0 ;  k = n → upper đúng bằng 1
```

**Clopper-Pearson ("exact")** — không có công thức đóng; bisection trên binomial, dùng `math.lgamma`. Coverage không bao giờ dưới nominal. Ngược trực giác: tại `k = n` **hẹp hơn** Wilson (100/100: 0.9638 vs 0.9630) và cần **ít mẫu hơn** (T=0.95: 72 < 73).

**Jeffreys (Bayesian)** — `posterior = Beta(k + 0.5, n − k + 0.5)`, lấy percentile 2.5 và 97.5. `0.5` là Jeffreys prior.

**Agresti-Coull KHÔNG có trong tài liệu** (grep 0 hit). Tài liệu chỉ có 4 method: `wilson`, `wilson-cc`, `clopper-pearson`, `jeffreys`. Trực giác "2 phantom trials" chính là ý tưởng nền của A-C nhưng tài liệu không gọi tên.

### 1.5 Cluster correction

```
deff  = 1 + (m − 1)·ICC        # m = số sample mỗi cluster
n_eff = n / deff               # rồi dùng n_eff thay n trong Wilson
```

ICC ANOVA estimator — **tính từ dữ liệu, không khai bằng tay** (dòng 1134–1140):
```
p̄   = total k / total n
MSB = Σ nᵢ(p̂ᵢ − p̄)² / (K − 1)              ← between-cluster
MSW = Σ nᵢ·p̂ᵢ(1 − p̂ᵢ) / (N − K)            ← within-cluster
n₀  = (N − Σnᵢ²/N) / (K − 1)
ICC = (MSB − MSW) / (MSB + (n₀ − 1)·MSW)    ← clamp [0, 1]
```

**Trần cứng** (dòng 1169): `m → ∞ ⇒ n_eff → K / ICC`. Thêm sample từ cùng nguồn **không** mua thêm được gì.

### 1.6 Judge correction

```
sens = TP/(TP+FN)          spec = TN/(TN+FP)
J    = sens + spec − 1                        # Youden's J
error amplification = 1/J

Rogan-Gladen:  p_true = (p_obs + spec − 1) / (sens + spec − 1)
```

### 1.7 So sánh 2 candidate

```
McNemar (cùng test set):
  b = A đúng B sai ;  c = A sai B đúng ;  n_disc = b + c
  Wilson trên b/n_disc → conclusive nếu interval KHÔNG chứa 0.5

Newcombe difference (khác test set):
  lower = (p̂₁ − p̂₂) − √( (p̂₁ − L₁)² + (U₂ − p̂₂)² )
  upper = (p̂₁ − p̂₂) + √( (U₁ − p̂₁)² + (p̂₂ − L₂)² )
  → conclusive nếu KHÔNG chứa 0
```

### 1.8 Bonferroni & rule of three

- K ≥ 5 strata → `conf_adjusted = 1 − alpha/K`. K=5 → 0.9900; K=10 → 0.9950; K=20 → 0.9975.
- Rule of three: 0 failure trong n trial → error rate có thể tới **≈ 3/n**. `0/30 → 0.1135`, `0/100 → 0.0370`.
- Composition tuần tự: `P(chuỗi đúng) = Π P(bước đúng)`. `0.95 × 0.90 = 0.8550`.

---

## 2. Probe-first

**Định nghĩa canonical** (glossary, dòng 3088):
> **probe-first** | The harness principle: run the real thing before building on a guess.

**Đầy đủ hơn** (`harness-contract.md:3`):
> **Probe before you build on a guess:** a load-bearing assumption that CAN be checked empirically — check it FIRST by RUNNING the real thing, before you design or build on it. A doc, `--help`, wiki, grep, or a chain of reasoning is a *hypothesis*, NOT a probe — never launder it as "probed"/"verified".

### Probe-first ≠ evidence-based

| | Probe-first | Evidence-based (nghĩa rộng) |
|---|---|---|
| Nguồn chấp nhận | **Chạy thật** cái thật | Doc, source, citation, reasoning chain |
| Doc / `--help` / wiki / grep | = **hypothesis**, KHÔNG phải probe | thường coi là evidence |
| Chuỗi lập luận | KHÔNG phải probe | có thể chấp nhận |
| Nhãn kết quả | OBSERVED (chỉ khi đã chạy) | tuỳ hệ |

Hành vi bị cấm có tên riêng: *"never launder it as 'probed'/'verified'"*.

### Vì sao probe-first ĐẶC BIỆT cần interval (dòng 96–124)

1. **Probe nhỏ.** 5, 10, 30 sample — không phải 5000. Đúng vùng mọi công thức đơn giản vỡ.
2. **LLM không deterministic** — dòng 112–113: *"Every LLM call is a random trial, and one successful run proves nothing about the next."*
3. **Ba vấn đề chỉ LLM mới có:** judge cũng là LLM (thước cũng cong); chọn 1 trong N prompt (bias); tune trên test set (mất independence).

### Probe design phải khai TRƯỚC khi chạy lệnh đầu tiên (dòng 2411–2416)

```yaml
probe-design:
  n: 100                # chốt trước, không chỉnh giữa chừng
  sources: 25           # số nguồn độc lập (K)
  threshold: 0.90       # ngưỡng cam kết
  route: cluster-floor  # do K quyết định, không do người khai
  peek: none            # không nhìn giữa chừng
```

---

## 3. Hệ 4 nhãn — `verification-mechanism.md:28–33`

| Label | Meaning | Allowed grammar |
|---|---|---|
| **OBSERVED** | Verified directly — ran it, read it, measured it — and nothing has changed since | "X is / does / returns …" |
| **DERIVED** | Follows from OBSERVED facts by a mechanism you can state | "X should / will / implies …" + the why |
| **PRIOR** | Training knowledge; may be stale | "X is typically … / was, as of …" |
| **ASSUMED** | Unverified and required by the conclusion | "assuming X — if wrong, then …" |

Nguyên tắc nền (dòng 25–26): **"The label IS the grammar: a claim's wording must never out-run its evidence tier."**

### Ánh xạ từ evidence ranking

`direct observation > reproduction > primary source > secondary source > memory`

- direct observation / reproduction → **OBSERVED**
- primary/secondary source **không chạy lại trong session này** → **PRIOR**
- memory alone → **ASSUMED**
- kết luận từ OBSERVED bằng mechanism phát biểu được → **DERIVED**

### Promotion / demotion — non-negotiable

```
ASSUMED  --[tool chạy thật]------→ OBSERVED
PRIOR    --[tool chạy thật]------→ OBSERVED
OBSERVED --[môi trường đổi]------→ PRIOR         (decay tự động)
OBSERVED --[mechanism nêu ra]---→ DERIVED       (claim mới)
BẤT KỲ   --[nói tự tin hơn]-----→ ✗ CẤM
```

> **Only a tool promotes a claim.** […] restating it more confidently does NOT — that is **a hallucination wearing OBSERVED grammar**, the most avoidable kind.

Nhánh thứ ba: *"'I don't know', followed by what would settle it, is a first-class answer."*

### 5 verification invariant

1. **Must be anchored** — SHA, `file:line`, hoặc real command output. Không anchor → `UNVERIFIABLE`.
2. **Downstream rejects UNVERIFIABLE** — gate coi claim không anchor **như không tồn tại**.
3. **Artifact is the source, not narration** — verdict ghi vào JSON máy đọc được.
4. **Self-report does not self-approve** — gate đọc artifact + policy, không tin "I PASS".
5. **Trace keeps a record.**

### Nhãn giao với interval — quy tắc TRUNG TÂM của workshop

Dòng 357–365:
> These three answer **"was it actually run"**. They do not answer **"how many times"**.
> `[OBSERVED] 3/3 pass` and `[OBSERVED] 300/300 pass` carry the same label, but one guarantees ≥43.9% and the other ≥98.9%.

Dòng 2918–2919:
> When a claim is a **rate**, `[OBSERVED]` is valid only with `k/n` and an interval. A bare `[OBSERVED] 92% accuracy` counts as a **malformed claim**.

Judge quyết định nhãn: judge pass gate → `[OBSERVED]` kèm ghi chú "judge error uncorrected"; judge fail → `[ASSUMED]`, exit 3; chưa calibrate → `[ASSUMED: judge uncalibrated]` và **dừng**.

---

## 4. Gắn interval vào claim

### 4.1 n = số item độc lập, KHÔNG phải số log line

```
Bẫy: 50 item × 10 lần chạy = 500 log line, nhưng n = 50.
n = 50   (46/50)   Wilson95 = [0.8116, 0.9685]  width 0.1568
n = 500  (460/500) Wilson95 = [0.8929, 0.9407]  width 0.0478  ← SAI, hẹp giả 3.3×
```
10 lần lặp vẫn hữu ích nhưng đo **thứ khác**: run-to-run stability. Report riêng.

Ba tầng n: `n` danh nghĩa → `n_eff = n/deff` → `K` (cluster floor). Judge có `n_calib` **tách biệt hoàn toàn**. McNemar có `n_disc = b + c`.

### 4.2 Route do K quyết định, KHÔNG do người khai (dòng 1279–1283)

| K | Route |
|---|---|
| K ≥ 20 | `icc` — ước ICC từ data, dùng `n_eff` |
| 10 ≤ K < 20 | `icc-upper` — lấy upper bound, bảo thủ |
| K < 10 | `cluster-floor` — 1 sample/cluster, **cấm đoán ICC** |

**Không có tham số `--icc` do user khai** — vì không hằng số default nào an toàn. Output **phải in ra route nào được chọn**.

### 4.3 Số quyết định = LOWER BOUND (dòng 449–453)

> The number used **to decide** is almost always the **lower bound**. It answers: *"how bad is the worst case?"*

Tại gate, report **hai số**:
```
Wilson lower bound = 0.8865      ← chuẩn chung
P(p ≥ 0.90)        = 0.9884      ← trả lời đúng câu hỏi thật
```
Chúng **có thể bất đồng**: `30/30` → Wilson FAIL, Bayesian PASS.

| Hậu quả | Tiêu chí |
|---|---|
| Ship đồ tệ rất đắt (tiền, an toàn, pháp lý) | **Wilson lower bound** |
| Chặn đồ tốt cũng đắt (trễ schedule) | **P(p ≥ T)** |
| Không rõ | Report **cả hai**, để người quyết |

### 4.4 Bảng dán tường — all-pass (k=n), Wilson 95%

```
  1/1   → ≥ 20.7%  (gần như vô nghĩa)     50/50  → ≥ 92.9%
  3/3   → ≥ 43.9%                         73/73  → ≥ 95.0%
  5/5   → ≥ 56.6%                        100/100 → ≥ 96.3%
 10/10  → ≥ 72.2%                        200/200 → ≥ 98.1%
 20/20  → ≥ 83.9%                        381/381 → ≥ 99.0%
 30/30  → ≥ 88.6%                        500/500 → ≥ 99.2%
```

min_n để lower bound chạm T (all-pass):
```
T=0.70 → 9    T=0.80 → 16   T=0.90 → 35   T=0.95 → 73   T=0.99 → 381
so sánh method @T=0.95:  Wilson 73 | CC 92 | CP 72 | Jeffreys 49
```

max_fails giữ lower ≥ 0.90:
```
n=30 → bất khả, kể cả 30/30      n=100 → tối đa 4      n=500 → tối đa 36
n=50 → tối đa 0                  n=200 → tối đa 11
```

Judge gate: `J ≥ 0.5` (không đạt → rejected, kết quả `[ASSUMED]`); `|sens − spec| ≤ 0.15` (không đạt → biased); `n_calib ≥ 50` tier 1, `≥ 200` tier 2. Judge dưới ~0.75/0.75 → `1/J ≥ 2×` → **reject, đừng correct**.

### 4.5 ABSTAIN

Tài liệu không dùng chữ "ABSTAIN" nhưng có đúng khái niệm dưới 4 dạng: `tie_within_noise`; `conclusive = False`; `[ASSUMED: judge uncalibrated]` + dừng; `n = 0 → (0.0, 1.0)`.

Cảnh báo (dòng 2961): **"A wide interval signals 'run more samples', not 'stop'."**

### 4.6 Mười câu hỏi trước khi tin một con số (dòng 2423–2473)

Hỏi **theo thứ tự**. Trượt bất kỳ câu nào → con số chưa sẵn sàng để quyết định.

1. **n thật là bao nhiêu?** Đếm item độc lập, không phải log line.
2. **Bao nhiêu nguồn độc lập?** K ≥ 20 → ước ICC; K < 10 → cluster floor.
3. **Đã stratify chưa?** Số quyết định là **stratum tệ nhất**. K ≥ 5 → Bonferroni.
4. **Ai chấm điểm?** AI judge chưa calibrate trên ≥50 balanced human-scored sample → `[ASSUMED]` và **dừng**.
5. **n có chốt TRƯỚC khi chạy không?**
6. **Con số này có phải "tốt nhất trong nhiều cái"?** Nếu có: select trên set A, report trên set B.
7. **Golden set đã qua bao nhiêu vòng tuning?**
8. **Đang so 2 candidate?** Cùng set → McNemar. Khác set → difference interval. **Không bao giờ** nhìn interval chồng nhau.
9. **Bao nhiêu bước tuần tự?** Nhân xác suất. 2 bước cùng model → **không** phải independent verification.
10. **Golden set khác production thế nào?** Viết 1 câu. Không viết được nghĩa là chưa biết.

### 4.7 Ba mức áp dụng — để mức 3 không giết mức 1

| Level | Khi nào | Câu bắt buộc |
|---|---|---|
| **1 · Exploratory** | Discovery probe, chưa xây gì lên nó | 1 và 10. Ghi `k/n` + Wilson |
| **2 · Report-grade** | Có người sẽ đọc và tin | 1–4, 8, 10 + stratification + cluster correction |
| **3 · Gate-grade** | Quyết định không đảo ngược được | Cả 10 + tier-2 judge calibration + `P(p≥T)` + prior provenance |

### 4.8 Bốn flag phải kiểm trước khi PASS

| Flag | Nghĩa |
|---|---|
| `saturated` | Interval chạm 0 hoặc 1 — đã **tràn**, không phải hẹp |
| `route = cluster-floor` | Quá ít nguồn độc lập |
| `judge = rejected / biased` | Thước không đạt chuẩn |
| `prior_used` | Dùng bằng chứng cũ — phải cite nguồn và w |

---

## 5. Anti-pattern — nguồn trực tiếp để cài lỗi vào bot

### A. Sai về con số
- **A1** Point estimate thay interval. `[OBSERVED] 80% accuracy` từ 8/10; sự thật 49%–94%.
- **A2** Bốn cách trực giác vỡ: 3/3→có thể 43.9% · 10/10→72.2% · 8/10→[49.0, 94.3] · 0/30→lỗi tới 11.4%.
- **A3** Dùng Wald ở small n — tràn ngoài [0,1] hoặc sụp thành điểm.
- **A4** n quá nhỏ cho câu hỏi đang hỏi. Golden set 30 mẫu **không bao giờ** chứng minh được ≥90%.
- **A5** Tin "Wilson95 = đúng 95%". Coverage thật ở n=10, p=0.30 là **0.9244**; sweep p cho thấy 40–58% giá trị p có coverage < 0.95, tệ nhất 0.9044. **n lớn hơn KHÔNG cứu.** Đọc "Wilson95" là "khoảng 92–95%".
- **A6** Đọc Wilson theo nghĩa Bayesian. SAI: *"95% xác suất p thật nằm trong [0.72, 1.00]"*. ĐÚNG: *"quy trình này, nếu lặp lại, sinh ra interval chứa p thật 95% số lần"*.
- **A7** Nhầm z one-tailed (2.33) với two-tailed (2.5758).

### B. Sai về mẫu
- **B1** Đếm log line làm n → width sai 3.3×.
- **B2** Bỏ qua clustering. E23: 100 trang từ **6 case file** → interval thật **rộng gấp 8.3 lần**.
- **B3** Thêm sample thay vì thêm nguồn. Trần `n_eff ≤ K/ICC`. Cùng 100 sample: 50 nguồn → n_eff 83.3; 2 nguồn → n_eff 9.3.
- **B4** Hằng số ICC mặc định. Dòng 1233–1234: **"No default constant is safe."**
- **B5** Ước ICC từ < 10 cluster → lệch thấp hệ thống → phạt ít hơn cần → lệch về phía nguy hiểm.
- **B6** Chỉ nhìn TOTAL, không stratify. TOTAL 92/100 đẹp nhưng stratum tệ nhất 17/20 chỉ đảm bảo ≥64%.
- **B7** Stratify quá tay không Bonferroni. 20 strata → **64.2%** xác suất có ≥1 báo động giả.
- **B8** Golden set thiên lệch. Dòng 2069–2070: *"A tight interval on a biased golden set is **more dangerous** than no interval at all."*
- **B9** Calibration set lấy ngẫu nhiên từ production → pass rate 95% → spec gần như không đo được. Phải cân bằng ~50/50.
- **B10** Dataset không có negative case. E09: chương trình **chỉ in `0`** cho mọi trang vẫn "13/19 đúng".

### C. Sai về LLM judge
- **C1** Tin số của LLM mà chưa đo LLM.
- **C2** Chỉ lưu accuracy, không lưu confusion matrix. Ba judge cùng acc ≈ 0.90 cho p_true 0.8277 / 1.0259 / 0.9375 — **chênh 0.11**.
- **C3** Clamp im lặng khi p_true vượt [0,1]. `1.0259` là **warning signal**, không phải số để cắt gọn.
- **C4** **Bẫy thị giác:** judge tệ trông như interval hẹp. Judge 0.70 có interval hẹp nhất bảng sau clamp (0.1305) nhưng raw width là **6.68** — hẹp vì đã tràn rồi bị cắt. Bắt buộc có saturation flag.
- **C5** Dùng judge J < 0.5 để back-correct. E23: J=0.4650 → `1/J = 2.15` → combined interval `[0.0000, 1.0000]`, vô thông tin.
- **C6** Hai judge cùng model. r = 0.8–1.0 → *"essentially one judge run twice"*.
- **C7** LLM check LLM coi là independent verification. *"wherever the model is wrong, it cannot catch itself."*
- **C8** Quên nhân xác suất qua chuỗi. `0.95 × 0.90 = 0.8550`.
- **C9** Vứt judge trượt gate. Sai — đổi **cách dùng**: pass → làm **thước**; fail → làm **chuông báo** gọi người.

### D. Sai về quy trình — tài liệu nói ĐÂY LÀ NGUY HIỂM NHẤT

Dòng 1865–1867:
> The traps below multiply the false-claim rate by **10×** and inflate scores by **0.10**. If you read only one section of this document, read III.5.

- **D1 Optional stopping.** *"The most dangerous trap for probe-first, because it describes exactly how people naturally work."* p=0.699 vs T=0.70: nhìn mỗi sample → **18.35%** false claim; nhìn 1 lần cuối → **1.92%**. Và *"the danger scales with how close you are to the threshold — which is exactly when you most want to look."*
- **D2 Winner's curse.** Mọi candidate cùng năng lực thật 0.80: N=5 → +0.0807; N=20 → +0.1257; N=50 → +0.1461. Dòng 1941–1943: **"Wilson computed on that same test set does NOT catch this bias."**
- **D3 Golden set leakage.** 1 vòng tuning → +0.0631; 5 vòng → +0.1033; 20 vòng → +0.1284. *"The golden set has become part of the model."*
- **D4 Garden of forking paths.** Không "chọn" gì cả, chỉ report cái đáng nói: 4 dimension → +0.0642; 8 → +0.0854; 16 → +0.1028. *"…while feeling entirely honest."*

### E. Sai khi so sánh
- **E1** So hai con số trần (80% vs 60% ở n=10) → đó là noise.
- **E2** ⚠️ **"Hai interval chồng nhau → không kết luận" là LỖI ĐỌC.** `90/100 vs 80/100`: interval chồng nhau nhưng difference interval `[+0.0001, +0.1995]` → **kết luận được**. Dòng 1809–1810: *"each separate interval has already 'paid' for its own uncertainty. Judging by overlap inadvertently double-counts that uncertainty."* Hậu quả: **bỏ lỡ cải tiến thật**. Tooling phải chống lại: *"there is no function named anything like `intervals_overlap()`"*.
- **E3** Dùng 2 interval độc lập khi cùng test set → vứt bỏ phần lớn power. Phải dùng McNemar.
- **E4** Noise band bằng hằng số bịa (`rel_band = 0.05`) — cùng bệnh với "default ICC 0.3".

### F. Sai meta — RỦI RO CAO NHẤT
- **F1 Cargo cult** (dòng 2968–2970): *"someone pastes an interval into a report, sees a number that looks scientific, and never reads IV.3.1. The harness trades one form of blind confidence for another — this one harder to argue with, because it has a formula."*

  **4 dấu hiệu đã rơi vào bẫy:** report có interval nhưng không nói n từ đâu · chưa ai từng thấy saturated interval hay `route = cluster-floor` · **mọi** judge đều "ok" · không có metadata về tuning rounds / candidates.

  **Phòng thủ duy nhất** (dòng 2982–2990): tool phải **lên tiếng khi có gì sai**, không chỉ in số. *"A silent number is easy to ignore. A line reading `WARNING: judge biased toward passing` is not."*
- **F2 Prior bịa / w quá lớn.** Sự thật 0.60, prior sai "450/500 = 0.90" → **kể cả 3000 sample vẫn chưa kéo về sự thật**. Never `w = 1.0`; tool phải raise khi `w > 0.5`.
- **F3** Bỏ qua judge calibration vì tốn công.
- **F4 Paralysis.** Interval rộng → không ai dám kết luận. Đáp: interval rộng nghĩa là "chạy thêm mẫu", không phải "dừng".

---

## 6. API contract (IV.7) — bản đồ để implement

```python
# basic
interval(k, n, conf=0.95, method="wilson") -> tuple[float, float]
    # method: "wilson" | "wilson-cc" | "clopper-pearson" | "jeffreys"
interval_full(...) -> dict   # {p_hat, z, center, half_width, lower, upper, width, conf, n, k, method}
coverage(n, p, conf, method) -> float        # tổng CHÍNH XÁC k=0..n, không simulation
min_n_all_pass(target, conf, method) -> int
max_fails(n, target, conf, method) -> int | None

# clusters
icc_anova(clusters: list[tuple[int,int]]) -> dict | None      # None khi K < 2
cluster_adjusted(clusters, conf) -> dict
    # route tự chọn theo K: >=20 "icc" | 10..19 "icc-upper" | <10 "cluster-floor"

# comparison
mcnemar_wilson(b, c, conf) -> dict     # conclusive = interval KHÔNG chứa 0.5
diff_newcombe(k1, n1, k2, n2, conf) -> dict   # conclusive = KHÔNG chứa 0

# judge
judge_screen(TP, FN, TN, FP, conf) -> dict    # verdict: "ok" | "biased" | "rejected"
rogan_gladen(p_obs, sens, spec) -> float | None   # None khi sens+spec <= 1
judge_adjust(k, n, TP, FN, TN, FP, conf, split=3) -> dict
    # PHẢI trả cả raw chưa clamp + saturated_low/high

# bayesian
jeffreys(k, n, conf) -> tuple[float, float]
posterior_prob_ge(k, n, T, prior_a=0.5, prior_b=0.5) -> float
prior_from_evidence(k_old, n_old, weight) -> tuple[float, float]
    # RAISE khi weight > 0.5
```

Ràng buộc: **pure stdlib** — chỉ `math`, `statistics.NormalDist`, `argparse`, `json`. Không scipy/numpy.

Exit codes: `0` ok / lower ≥ threshold · `1` lower < threshold · `2` invalid input · `3` **judge rejected** (kết quả không đủ tư cách `[OBSERVED]`).

### Bug có thật, phải có test (dòng 2682–2686)

> **This bug was hit for real while writing this document.** Chia sau (`integral / exp(logB)`) làm `exp(logB)` underflow về 0 khi `a+b ≥ 500` → `ZeroDivisionError`. Phải ở trong log space: `exp(log_integrand − logB)`.
> This is a **mandatory test case**, not an optional detail.

### Regression anchor — dùng làm test vector

```
interval(8, 10, 0.95, "wilson")             == (0.490162, 0.943318)
interval(8, 10, 0.95, "wilson-cc")          == (0.442200, 0.964600)
interval(100,100,0.95,"clopper-pearson")[0] == 0.963800    # hẹp hơn wilson 0.963000
interval(10, 10, 0.95, "jeffreys")[0]       == 0.782804
coverage(10, 0.30, 0.95, "wilson")          == 0.924403 (±1e-5)
coverage(10, 0.99, 0.95, "wilson")          == 0.9044   (±1e-4)
icc_anova([(20,20),(20,20),(19,20),(8,20),(5,20)])["icc"] ≈ 0.5619
min_n_all_pass(0.95, "wilson") == 73 | "clopper-pearson" == 72 | "jeffreys" == 49
diff_newcombe(90,100,80,100) → lower ≈ +0.0001, conclusive = True
posterior_prob_ge(30, 30, 0.90) ≈ 0.9884
judge_screen(TP=9, FN=4, TN=17, FP=5) → youden_j ≈ 0.4650, verdict = "rejected"   # dữ liệu THẬT từ E23
```

⚠️ Tài liệu tự cảnh báo (dòng 2898–2905): các anchor này do chính probe đó sinh ra → **chỉ bắt regression, không chứng minh công thức đúng**. Cần thêm cross-check với `scipy.stats.binomtest(...).proportion_ci()`, round-trip test Rogan-Gladen, và property test (đơn điệu theo conf; đối xứng `wilson(k,n) ↔ wilson(n−k,n)` quanh 0.5).

### Edge case bắt buộc

`n=0 → (0.0, 1.0)` không raise · `k=0 → lower đúng 0.0` · `k=n → upper đúng 1.0` · `k>n`/`k<0`/`n<0` → `ValueError` · `conf ∉ (0,1)` → `ValueError` · `k,n` không phải int → `TypeError` · `icc_anova` K<2 → `None` không raise · `icc_anova` MSB<MSW → ICC clamp 0.0 không âm · `cluster_adjusted` K=5 → route `cluster-floor` KHÔNG phải icc · `mcnemar_wilson(0,0)` → `conclusive=False`, `(0.0,1.0)` · `judge_screen` TP+FN=0 → `rejected` · `judge_adjust` J≤0 → `[0,1]` + rejected, không chia 0 · `prior_from_evidence(90,100,1.0)` → `ValueError`.

---

## 7. Mẫu báo cáo một claim (dòng 2477–2495) — dùng làm chuẩn cho bot

Thay vì `[OBSERVED] pipeline achieves 92% accuracy`, viết:

```
[OBSERVED] golden-100, human-scored, n fixed before the run
  design:         5 strata × 20, 47 independent sources (K=47 → route icc)
  total:          92/100   Wilson95 = [0.8500, 0.9589]
  worst stratum:  17/20    Wilson95 = [0.6396, 0.9476]  (handwriting)
                           Bonferroni K=5 → [0.5644, 0.9612]
  → guarantees only ≥ 56% on handwriting (after multi-stratum correction)
  → P(p ≥ 0.90 | data) = 0.7393   [Jeffreys prior, no prior evidence used]
  → golden set lacks: phone photographs, aged yellowed documents
  → golden set has seen 3 tuning rounds
```

> Considerably longer. But **the first line is marketing; the rest is engineering.**

---

## 8. Trích dẫn verbatim để dùng trong workshop

1. **dòng 65–67** — *"The break is in the **step from '8/10' to '80% accuracy'**. That step feels so obvious that nobody thinks of it as a step. But it is one, and it has no basis."*
2. **dòng 79–80** — *"The number 80% is not wrong. It merely **hides the most important thing**: you do not know it is 80%."*
3. **dòng 112–113** — *"**LLMs are not.** Same prompt, same input, different results. Every LLM call is **a random trial**, and one successful run **proves nothing** about the next."*
4. **dòng 449–453** — *"The number used **to decide** is almost always the **lower bound**."*
5. **dòng 498–500** — *"This is a **feature, not a bug**. It means Wilson **refuses to believe anything absolutely** based on a handful of samples."*
6. **dòng 1865–1867** — *"The traps below multiply the false-claim rate by **10×** […] If you read only one section of this document, read III.5."*
7. **dòng 1941–1943** — *"**Wilson computed on that same test set does NOT catch this bias.** Rule: select on set A, report on set B."*
8. **dòng 1809–1810** — *"each separate interval has already 'paid' for its own uncertainty. Judging by overlap inadvertently double-counts that uncertainty."*
9. **dòng 2069–2070** — *"A tight interval on a biased golden set is **more dangerous** than no interval at all, because it creates the impression of careful measurement."*
10. **dòng 2968–2970** — *"someone pastes an interval into a report, sees a number that looks scientific, and never reads IV.3.1. The harness trades one form of blind confidence for another — this one harder to argue with, because it has a formula."*
11. **dòng 2918–2919** — *"When a claim is a **rate**, `[OBSERVED]` is valid only with `k/n` and an interval. A bare `[OBSERVED] 92% accuracy` counts as a malformed claim."*
12. **dòng 1233–1234** — *"'safe' depends on the very thing you do not know. **No default constant is safe.**"*

---

## 9. Khoảng trống — thứ tài liệu KHÔNG cho, ta phải tự viết

Tài liệu tự đánh dấu UNRESOLVED (IV.10): Q6 (ngưỡng "cluster pass" — *"could recreate exactly the problem the cluster floor exists to avoid"*), Q9 (bảng prior weight là **judgement call, không dẫn từ dữ liệu** — *"occupies exactly the position that 'default ICC = 0.3' held before being refuted"*), Q8 (golden set hết hạn sau bao nhiêu vòng), Q7 (CP có nên làm default cho all-pass). **Q3 và Q4 khuyết hoàn toàn** khỏi văn bản (nhảy Q2 → Q5, dòng 3000→3004) — có vẻ lỗi biên tập.

Phải tự viết: công thức đóng Clopper-Pearson (chỉ có mô tả bisection) · thuật toán Beta quantile / regularized incomplete beta · cách tính "upper bound của ICC" cho route `icc-upper` (chỉ nói "take its upper bound", không nói bằng phương pháp nào) · chi tiết corner-envelope Bonferroni 3 chiều trong `judge_adjust` · Agresti-Coull (vắng mặt hoàn toàn).

## 10. Ba việc rẻ nhất chặn được nhiều nhất (IV.11)

Nếu workshop chỉ kịp dạy 3 thứ:

1. **Ba dòng metadata cho mọi probe** — n chốt trước / số candidate đã thử / số vòng tuning. Chặn 3 bẫy nguy hiểm nhất (D1, D2, D3), chi phí ~0.
2. **`wilson.py` bản tối thiểu** — `interval` + `cluster_adjusted` + `judge_screen`.
3. **Sửa prompt judge** để chứng minh phương pháp chạy được trên dữ liệu thật (E23: J 0.4650 → ~0.6468 bằng cách sửa 4/5 ca false rejection, không cần chạy lại probe nào).
