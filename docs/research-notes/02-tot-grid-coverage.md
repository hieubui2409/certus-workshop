# Research note 02 — ToT × Grid Coverage

**Nguồn:** `/home/hieubt15/Documents/vsf/sdlc-harness/docs/research/feature/tot-grid-coverage/`
(README.md, DEBTS.md, harness/scripts/, harness/data/, harness/agents/, harness/adapters/, build/design/, goals/, library/)

---

## 0. Ba cảnh báo phải đọc trước

**(a) "ToT grid" KHÔNG phải cấu trúc cây.** Tên thư mục ghép hai thứ rời nhau:

- **ToT (Tree of Thoughts)** xuất hiện **đúng một lần** trong toàn pipeline — ở bước chọn dynamic axes. Không phải ở coverage.
  `harness/scripts/axis_search.py:1-2`: *"axis_search.py -- the ONE Tree-of-Thoughts beam/prune in the whole pipeline"*. Có hẳn test `tests/test_one_tot_only.py` ghim luật này.
- **Grid** là **lưới tổ hợp t-wise**, phẳng, không phải cây.

**(b) Mục tiêu không phải đo coverage.** `README.md:27`:
> **Không.** Mục tiêu là **quyết định có được phép phát hành hay không**.

**(c) Wilson interval KHÔNG có ở đây.** `grep -rli "wilson|binomial|clopper|rule of three"` → **0 kết quả**. Từ `confidence` có xuất hiện nhưng nghĩa hoàn toàn khác: một mapping cố định band→[0,1] **chỉ dùng sắp thứ tự queue probe, không bao giờ là gate**.

---

## 1. Vấn đề mà line/branch/mutation coverage không giải quyết

`README.md:83-92` — luận điểm trung tâm:

> Bộ kiểm của bạn chạy 6 tình huống. Kiểm thử đột biến gài lỗi vào mã, chạy 6 bài đó, báo **"92% — tốt lắm"**.
>
> Con số 92% đó **đúng**, và **vô nghĩa**: nó là 92% của 6 tình huống, không phải của 24. Mười tám tình huống kia không nằm trong mẫu số. **Kiểm thử đột biến không có mẫu số về không gian rủi ro** — nó chỉ có mẫu số về những dòng mã mà bài kiểm đã chạm.
>
> **Cái lưới chính là mẫu số đó.**

| | Mẫu số là gì | Điểm mù |
|---|---|---|
| Line coverage | các dòng code có tồn tại | không biết một dòng chạy đúng trong bao nhiêu **ngữ cảnh** |
| Branch coverage | các nhánh trong 1 hàm | không biết **tương tác giữa nhiều biến** (bug bậc 2, bậc 3) |
| Mutation testing | mutant gieo vào code **mà test đã chạm** | *"nó không biết cái nó không biết"* (`README.md:52`) |
| **Grid coverage** | **không gian rủi ro** = mọi tổ hợp t-wise của axes, có trọng số | vẫn cần axes do người/model đề xuất |

Sơ đồ tổng (`README.md:137-146`):
```
kiểm thử đột biến  →  "bộ kiểm của mày có bắt được lỗi không?"  →  một con số
                                     │
                                     ▼
tot-grid-coverage  →  "còn góc rủi ro nào chưa ai nhìn không?"  →  chặn / không chặn
                      ├─ lưới       = danh sách các góc + trọng số   (mẫu số)
                      ├─ đột biến   = cái cân, gác cửa ô mức-cao ở vùng chặn
                      ├─ DST        = lấp ô mà bài kiểm thường không với tới (thứ tự)
                      └─ cái lồng   = thứ viết bài kiểm không được tự chấm mình
```

---

## 2. Cấu trúc grid

### 2.1 Axes

**Fixed axes** — khai trong config, mỗi cái có `ref` trỏ tới **enum/constant/config field có thật trong code**, resolve được bằng `--resolver-command`.
**Dynamic axes** — do model đề xuất, phải qua `admit.admit_axis()`.

Điều kiện admission (`goals/harness-build-brief.md:101`):
> real resolvable `ref` (not `asserted`), ≥2 reachable values *in the measured domain*, orthogonal (reject collinear MI>~0.7), hard `m_cap`, every rejection logged with reason.

### 2.2 Cell

`harness/scripts/cells.py:3-4`:
> "axes" is an ordered mapping axis-name → list of values. A "cell" is (axis-name-subset, value-tuple): one full assignment to a chosen t-subset of axes.

**Cell id canonical, không tự do đặt** (`harness/README.md:394-397`):
> `cell:<axis>=<value>|<axis>=<value>` — every axis of the cell, in the order the axis lock holds them, joined with `|`, prefixed with `cell:`. That exact string is the ledger claim id, the grid id and the report row; **nothing else is**.

### 2.3 Zones — chiều thứ hai

Zone = predicate trên axis values, có weight `w`, **first-match-wins**. `harness/scripts/zones.py:1-10`:
> A zone is `{"id": str, "when": {axis_name: value | [values...]}, "w": number}`. Matching walks the caller-supplied `rules` list IN ORDER and returns the first zone whose predicate matches — **reordering two rules that both could match the same cell genuinely changes that cell's zone**. An axis named in `when` that is absent from the cell being matched … simply fails to match that rule — it never raises.

Hai ngưỡng điều khiển downstream:
- `zones.blocking_w` — sàn để zone thuộc **release-blocking set**
- `zones.hot_w` — sàn để zone là **hot** (escalate lên t=3)

Guard chống lách (luật `B18`): `zones --compile` **từ chối** nếu không rule nào chạm `blocking_w` — *"the graded party must not be able to empty the blocking set"*.

### 2.4 Sinh grid — code trích nguyên văn

```python
def count_cartesian(axes):
    """Full product size — 1 for zero axes (empty product), not an error case."""
    return math.prod(len(values) for values in axes.values())


def enumerate_t_wise(axes, t, exclude=None):
    """Lazily yield every t-wise cell. `exclude(cell) -> True` drops that cell.
    Deterministic: iteration order follows dict insertion order of `axes`."""
    names = list(axes.keys())
    if t <= 0 or t > len(names):
        return
    for combo_names in itertools.combinations(names, t):
        value_lists = [axes[name] for name in combo_names]
        for values in itertools.product(*value_lists):
            cell = (combo_names, values)
            if exclude is not None and exclude(cell):
                continue
            yield cell


def count_t_wise(axes, t, exclude=None):
    """Unconstrained: closed form — elementary symmetric sum e_t of axis sizes.
    For t=2 collapses to (S^2 - sum(a_i^2)) / 2. Valid ONLY when no predicate
    excludes cells — an `exclude` present means the closed form no longer holds,
    so this counts via full enumeration instead (no silent approximation)."""
    if exclude is not None:
        return sum(1 for _ in enumerate_t_wise(axes, t, exclude=exclude))
    sizes = [len(values) for values in axes.values()]
    if t <= 0 or t > len(sizes):
        return 0
    return sum(math.prod(combo) for combo in itertools.combinations(sizes, t))
```

Công thức chốt:
```
|cells|_{t=2} = (S² − Σᵢaᵢ²) / 2 ,  với S = Σᵢaᵢ
```

Ví dụ nén thật (`corpus-map.md:61`): 10 trục cỡ `3,4,5,4,4,4,5,4,4,3` → `S=40`, `Σaᵢ²=164` → Cartesian **921.600** vs t=3 toàn cục **~11.400** vs t=2 **718** vs t=2 trừ N/A **711**. Nén **1.283×**.

### 2.5 Schema `grid-state.schema.json` — trích nguyên văn

```json
{
  "title": "grid.json cache",
  "description": "state/grid.json -- the ONLY artifact grid_state.write_bands() may produce ... A CACHE (L3): every field here is re-derived from the ledger + coverage + admission log + stub registry at projection time; nothing on this file is itself a source of truth.",
  "required": ["cells", "inputs_digest", "self_sha256"],
  "additionalProperties": false,
  "properties": {
    "cells": {
      "additionalProperties": {
        "required": ["band", "source", "flags", "evidence_id"],
        "properties": {
          "band":   {"enum": ["high", "med", "low", "stub", "N/A", "unknown"]},
          "source": {"const": "projected",
                     "description": "always literally 'projected' -- the one value write_bands() accepts; anything else is refused before it ever reaches disk."},
          "flags":  {"type": "array", "items": {"type": "string"}},
          "evidence_id": {"type": "array", "items": {"type": "string"},
                     "description": "the ledger/coverage record hash(es) this band rests on; empty for the DEFAULT row (no evidence at all)."}
        }
      }
    },
    "inputs_digest": {"description": "opaque {name: digest} snapshot ... to detect staleness"},
    "self_sha256":   {"pattern": "^sha256:[0-9a-f]{64}$"}
  }
}
```

`axes-lock.schema.json` — mỗi axis là `{ref, values}` hoặc `{refs, values, values_by_ref}`:
> never a value a model assigned directly; every entry traces back to a `resolve_ref()` call the caller supplied. **An entry naming no reference at all is invalid in both forms: that is the shape this lock exists to exclude.**

---

## 3. Tính coverage trên grid

### 3.1 Band projection — bảng 17 hàng, trái tim của hệ

`build/design/architecture.md:477-497`. **Bảng phải TOÀN PHẦN — mọi quan sát rơi vào đúng một hàng.**

| Quan sát | Band | Cờ |
|---|---|---|
| probe pass + `cov_cell` chạm `code_path` + ≥2 assert độc lập (AST) + **zone chặn**: có `mutation_run` `killed` khớp seed | `high` | — |
| như trên nhưng **zone KHÔNG chặn** | `high` | `mutation_sampled` |
| như trên, **zone chặn** mà THIẾU `mutation_run` hợp lệ | `unknown` | `mutation_missing` |
| như trên, **zone chặn** mà mutant **SỐNG SÓT** | `unknown` | `mutant_survived` = `false_high` |
| như trên, **zone chặn**, có `killed` neo đúng vòng nhưng **binding KHÔNG đủ 5 trường** | `unknown` | `mutation_missing` + `mutation_unbound` |
| như trên, **zone chặn**, CÙNG vòng seed đã có `survived` rồi sau đó có `killed` | `unknown` | `mutant_survived` + `mutation_round_conflict` |
| probe pass + chạm nhưng artifact **không khớp `probe_sha256`** | `unknown` | `probe_binding_mismatch` |
| pass + chạm, số assert **dưới bar đã siết** bởi calibration | `med` | `high_bar_tightened` |
| ô lẽ ra `unknown` **không mang cờ nào** và đang có stub TTL còn sống | `stub` | `stubbed` |
| pass + chạm `code_path`, **1** assert | `med` | — |
| pass + chạm `code_path`, **0** assert | `unknown` | `no_assertion` |
| probe pass nhưng `cov_cell` KHÔNG chạm, **và `cov_suite` cũng KHÔNG** | `unknown` | `coverage_mismatch` |
| `code_path` có trong `cov_suite`, VẮNG trong `cov_cell` | `low` | `incidental` |
| `cov_cell` chứa dòng KHÔNG có trong `cov_suite` | `unknown` | `coverage_inconsistent` |
| probe fail (`test_exit_code != 0`) | `low` | `known_failure` |
| `outcome == unresolved` (thiếu/hỏng `result.json`, nonce lệch) | `unknown` | `unresolved_probe` — **không bao giờ pass** |
| không có record bound nào cho ô | `unknown` | — (mặc định) |

Nguyên tắc **S1∩S2** để đạt `high`: test đã chạy **AND** coverage xác nhận dòng đó **AND** assert nhắm đúng hành vi của cell.

Implementation: `harness/scripts/project_cell.py:27-190` — if-chain thuần, **thứ tự nhánh là load-bearing**.

### 3.2 Hai con số rollup — KHÔNG BAO GIỜ gộp

`harness/scripts/rollup.py:1-15`:
> **Two numbers that must NEVER merge into one.** `risk_weighted_coverage()` is a **DIAGNOSTIC trend indicator only** — never a gate input, never fed into a stop/release decision anywhere. `min_per_zone()` is what a gate actually reads: the WORST band present in EACH zone, as a per-zone structure — **never collapsed into a single average, because an average lets one high zone hide a low in a completely different zone**.
>
> This module deliberately exposes **no third function** that combines the two into a scalar — see `test_rollup.py::test_module_exposes_no_single_scalar_summary_of_overall_coverage`, which enumerates every public callable here and **fails the build the moment anyone adds one**.

```
RWC = Σ_{c ∉ N/A} w(c)·band_score(band(c))  /  Σ_{c ∉ N/A} w(c)      ← chỉ tham khảo

gate(z) = min_{c ∈ z, band(c) ≠ N/A} band_score(band(c))              ← cổng thật
```

```python
def risk_weighted_coverage(cell_records, band_scores) -> dict:
    """DIAGNOSTIC ONLY. Returns {"value": float|None, "cells_total",
    "cells_scored", "cells_excluded_na"} -- never a bare float. `value` is None
    when every cell was excluded -- reporting 0.0 there would misrepresent
    "no data" as "measured and zero"."""
```

`band_score` là **DATA trong config**, không phải hằng số:
```
[{"band":"high","score":1.0}, {"band":"med","score":0.6}, {"band":"low","score":0.2},
 {"band":"stub","score":0.0}, {"band":"unknown","score":0.0}]
```
`N/A` **không có entry** — bị loại hoàn toàn, không bao giờ chấm 0.

### 3.3 Xử lý N/A — quy tắc rất cụ thể

`rollup.py:24-33`:
> N/A excluded from BOTH numerator and denominator — **"not applicable" is not "average risk zero"** — and excluded from a zone's own worst-band computation for the identical reason. Both report `cells_excluded_na` so a caller can **SEE** the exclusion instead of having it silently absorbed.

**N/A chỉ vào qua MỘT cửa** — `constraints.yaml` đã qua `admit_constraint()`. **Bốn nguỵ biện bị từ chối thẳng** (`harness/agents/axis-proposer.md:47-51`): `rare`, `hard_to_test`, `few_users`, `system_will_block`.

`harness/README.md:183-186`:
> "Rare", "hard to test", "niche" and "the system would block that anyway" are not constraints; they are **untested cells with an excuse**, and they are rejected as such.

**Ba lỗi thật đã đo được về N/A:**

1. **N/A + executed ⇒ `NAConflictError`** — *"because the denominator's integrity is the whole point"*.
2. **Zone toàn N/A biến mất khỏi báo cáo** (`rollup.py:35-45`): *"Measured: ONE accepted N/A on the only cell of the heaviest blocking zone (w=0.95) removed that zone from the number this module's own docstring calls THE gate, and the run reported PASS with nothing anywhere saying a zone had left."* → fix bằng `ZoneWithoutScoreableCellsError`.
3. **Zone weight conflict ⇒ `ZoneWeightConflictError`** — không average, không max, không first-wins. Lý do đo được: một cell mang `w=0.9` nằm trong zone báo `w=0.1` ⇒ cả zone tụt dưới `blocking_w` và **thoát khỏi release block**.

### 3.4 Thứ tự probe

```
priority(cell) = w(zone) × (1 − confidence(cell))
```
`confidence` là mapping cố định trong config, **chỉ để sắp queue, không bao giờ là gate**.

---

## 4. Mutation testing & DST

### 4.1 Mutation — bị hạ cấp

`README.md:98-99`:
> Kiểm thử đột biến **không bị thay thế**. Nó bị **hạ cấp thành một điều kiện, trong một ô, của một cái lưới**. Nó là cái cân, không phải bảng điểm.

**Hai chế độ, không phải một tỉ lệ:**

| Vùng | Luật | Thiếu thì sao |
|---|---|---|
| zone chặn (`w ≥ blocking_w`) | **MỌI ô `high` phải có `mutation_run` `killed`** — không lấy mẫu, không ngoại lệ; binding đủ 5 trường; trong một vòng seed thì `survived` đã ghi **không bị** `killed` lật sau | ô rơi `unknown` + `stop_gate (i)` chặn |
| zone không chặn | lấy mẫu theo `calibrate.sample_rate`, chọn bằng seed | report in cỡ mẫu; cờ `mutation_sampled` |

**Mutation score dùng theo hai cách khác nhau, không phải một tỉ lệ toàn cục:**
1. **Per-cell, binary, như gate condition** — cell `high` trong blocking zone ⇔ tồn tại `mutation_run` `verdict=pass`, `seed_id` khớp vòng calibration hiện tại, **và** `is_bound()`.
2. **Aggregate, như calibration number** — `false_high_rate = survived / total`.

Operators là **AST node types, generic** (`mutate.py:9-15`): *"zero SUT name, zero per-project tuning, zero domain assumption baked in."* Cố tình **không** swap boolean operators — `and`/`or`/`not` có thể đổi short-circuit order làm crash code không liên quan.

**Đòn tautology bị giết ở đây** (`project.py:57-61`):
> a probe whose every assert is trivially true can still get bound + pass + touch every line, but **a blocking-zone high band simply does not exist as a reachable branch of this function** without a killed, seed-anchored, BOUND mutant.

### 4.2 DST

`README.md:110-116`:
> Kiểm thử đột biến sửa **mã**. Con lỗi này không nằm trong mã nào cả — mọi dòng đều đúng. Nó nằm ở **thứ tự thi hành**, thứ do hệ điều hành quyết chứ không phải mã của bạn. Không thể gài đột biến vào một thứ không phải là mã.
>
> Tệ hơn: giả sử bạn **có** gài đột biến vào một hàm dính tới lỗi này. Chạy bộ kiểm — xanh, đột biến "sống sót". Kiểm thử đột biến kết luận *"bài kiểm của bạn yếu ở chỗ này"*. **Sai luôn cả chẩn đoán.**

Tích hợp qua **trục `interleaving`**; cầu nối là field **`cell_touched`** trong ledger record.

**RNG là sha256 counter stream, KHÔNG phải `random.Random(seed)`** (`dst_scheduler.py:3-7`):
> Both are reproducible within one CPython build; **only the hash stream is reproducible ACROSS builds** and provably independent of interpreter state.

**Ba lớp chống nguồn ngẫu nhiên ẩn:**
```
P1 static  -- AST scan của adapter + mọi oracle lúc admission. Bắt nguồn khai báo, trượt nguồn gián tiếp.
P2 canary  -- chạy CÙNG seed trong HAI PROCESS RIÊNG rồi so byte. Bắt hầu hết rò thật.
P3 sampling-- replay một phần seed ĐANG PASS. Bắt rò hiếm theo thời gian, không bao giờ đạt xác suất 1.

P2 phải là hai process. Gọi lần hai trong cùng interpreter dùng chung module globals,
warm cache và một hash seed → giấu đúng lớp state dependence đang đi săn.
"This is the easiest place in the whole engine to fool yourself."
```

**ToT là công cụ SAI cho DST** — brief nói thẳng: *"a value function on a partial schedule prefix does not exist"*. Shrink dùng **deterministic bisection (ddmin)**.

### 4.3 Calibration seed — thứ tự load-bearing

```
calibrate --open:
  ledger_closed_digest = sha256( mọi dòng ledger tính tới thời điểm đóng sổ )
  calib_nonce          = secrets.token_hex(16)   # do CHÍNH bước gate sinh, 0 call model
  calib_seed           = sha256( ledger_closed_digest || calib_nonce )
```

`calibrate.py:32-36`:
> hash the ledger AS IT SITS RIGHT NOW, **THEN** mint the nonce — reversing that order would let the nonce influence what gets hashed, which is exactly the "predictable before the fact" hole v2's `seed = hash(grid)` defect left open (RTB-4).

Lỗ v2 rất đáng dạy: seed cũ là `hash(grid)`, mà `grid.json` nằm trên đĩa và model **đọc được** (chỉ bị cấm ghi) ⇒ người viết probe **tính trước được** danh sách ô sẽ bị kiểm.

Ba loại rate cần đo: `false_high` / `false_N/A` / `false_prune`, bằng cách hồi sinh ~10% cell đã bị gọi là high/N-A/pruned. *"This is the single number that says whether the whole machine is trustworthy; ~15% is the threshold that changes beam/theta."*

---

## 5. ToT axis search — thuật toán

### 5.1 Objective function

```
V(A)      = Σ w(cell) trên các cell Cartesian đầy đủ mà A sinh ra
cost(A)   = λ · |cells(A)|
ρ(A, x)   = ( V(A ∪ {x}) − V(A) ) / ( |cells(A ∪ {x})| − |cells(A)| )
```

Axis có ρ dưới θ là `dominated` → **quarantine, không bao giờ xoá**.

`score.py:10-18` — **lỗi Goodhart có thật, không phải strawman:**
> `naive_score(A) = V(A) − cost(A)` grows almost every time an axis is added, because a linear cost term (λ=0.02) rarely outweighs even a small positive value increment; the "dominated" branch built on it **essentially never fires**. ρ instead normalizes by how many NEW cells the candidate adds, so a high-cardinality axis that mostly dilutes into a low-weight catch-all zone correctly reads as dominated even though its raw value-minus-cost keeps climbing.

`marginal_risk_density()` raise `DegenerateMarginalError` khi mẫu số < ε — *"rather than dividing by (near-)zero and reporting a meaningless number"*.

### 5.2 Beam search — không gian là LATTICE

`axis_search.py:17-20`:
> Search space: a node is the SET (frozenset) of dynamic axis names locked into it so far — **a LATTICE, not a tree**. Reaching the identical set via two different insertion orders (a→b→c and c→a→b) is the SAME node, visited exactly once.

**Quarantine-not-delete với `revisit_if` load-bearing:**
> An axis found dominated is appended to `state/quarantine.jsonl` — **never dropped**. It carries a `revisit_if` condition, and that stored condition is **LOAD-BEARING, not decoration**: at the end of every round this module recomputes ρ for every quarantined axis against that round's best node, then READS the condition back off the record and revives ONLY if `revisit_verdict()` says it is met. **A condition whose type this build cannot re-check is NEVER treated as met** — an unverifiable condition blocks the revive instead of silently falling through.

**Progressive widening + 3 budget caps:**
```python
def beam_width_for_depth(depth, *, shallow_width, deep_width, shallow_depth_limit):
    """Wide at shallow depth, narrower past the limit -- schedule lives in config,
    never a harness constant."""
    return shallow_width if depth < shallow_depth_limit else deep_width

def select_beam(children, *, width):
    """Deterministic total order: value descending, ties broken by the sorted
    dynamic-axis-name tuple ascending."""
    return sorted(children, key=lambda c: (-c["value"], sorted(c["dynamic"])))[:width]

def check_budget(*, elapsed_s, max_wall_clock_s, nodes_expanded, max_nodes,
                 tokens_used, max_tokens_total):
    """Name of the FIRST cap at/past its ceiling (fixed order: wall-clock, nodes,
    tokens), or None. A cap <= 0 means "not enforced", not "already exhausted"."""

def budget_used_fraction(...):
    """MAX used-fraction across the three caps -- whichever is closest to
    exhausted drives the greedy collapse."""

def resolve_beam_width(depth, ..., used_fraction, greedy_threshold_fraction):
    """Past the greedy threshold the beam collapses to exactly one, REGARDLESS of
    the depth schedule -- anytime, best-so-far-preserving greedy mode."""
    if used_fraction >= greedy_threshold_fraction:
        return 1
```

Giá trị tham khảo (**tunable, không phải hằng số**): `θ=0.35→0.28`, `λ=0.02`, `EPS=1e-6`, `MI>0.7` reject collinear, `m_cap=4`, `BEAM=3→4`, widening `k=5 (depth<2) → k=2`, greedy threshold `0.75`.

### 5.3 Escalation t=2 → t=3 — hai tầng lọc

`escalate.py:1-15`:
> **Stage 1** keeps only axes that TOUCH a hot zone. **Stage 2** enumerates every t=3 combination of ONLY those hot axes and keeps a candidate cell only when **its OWN actual zone match** itself reaches `w ≥ hot_w`: an axis can touch a hot zone in general while a SPECIFIC value-triple of it still lands in a cold catch-all zone, and that triple must not survive. Two-stage narrowing buys ~11.400 → ~140 cells (**~81×**).

**Bẫy đã đo được — hai degree, không phải một:**
> One key serving both jobs makes the corpus's own "base t=2, escalate to t=3 in hot zones" **inexpressible**: measured on a real 4-axis run, at a shared t=2 all four escalation survivors were already cells of the base grid, so **the pass added nothing while looking like it had run**.

**Dedup KHÔNG được loại triple chỉ vì 3 cặp con đã resolved ở t=2:**
> doing that would silently discard exactly the **pure order-3 defect class** (a genuine three-way interaction bug invisible at every pairwise slice) that t=3 escalation exists to catch — **an anti-Goodhart regression dressed up as a dedup**.

---

## 6. Prompt templates — trích nguyên văn

### 6.1 `propose-axes.md` (toàn văn)

```markdown
# Propose input dimensions worth varying

You are reading a codebase you did not write. You have read-only tools.

Your job is to propose **dimensions of input that this code branches on** --
things that can take one of several concrete values, where different values
plausibly take different paths through the code. Nothing else.

You do not rank them. You do not say which matters most. You do not judge
anything. Something else does that from real executions; your reply is one
list of candidates and their reasons.

## What already exists

Dimensions already accepted (do not repeat these):
{{ALREADY}}
Dimensions rejected earlier, with why (do not repeat these either):
{{REJECTED}}

## What makes a candidate usable

Each candidate needs three things, and a candidate missing any of them is
thrown away without being read:

1. **`name`** -- a short identifier, lower_snake_case.
2. **`ref`** -- a pointer, as a string, to where the set of possible values
   is DEFINED IN THE CODE: a symbol path, an enum, a constant, a config
   field. It has to be resolvable by reading the repository. A `ref` you
   invented, or one that names a value rather than the definition of the set
   of values, is the single most common reason a candidate is discarded.
3. **`values`** -- the concrete values you believe that ref resolves to. At
   least two. If you can only find one, the dimension does not vary and does
   not belong in this list.

Add `provenance_tier` to each candidate. It must be one of exactly these
four words -- `executed`, `retrieved`, `derived`, `asserted`:

- `retrieved` -- you read the definition in a file. Use this for almost everything.
- `derived`   -- you inferred the set from more than one place.
- `asserted`  -- you believe it but cannot point at it. Expect it to be refused.
- `executed`  -- reserved for something that ran. You did not run anything,
                 so do not use it.

## What to reply with

One JSON object, nothing else. No prose before it, no prose after it, no
code fence. It must be the last thing you write and the only thing you write.

{"nonce": "{{NONCE}}", "candidates": [{"name": "...", "ref": "...", "values": ["...", "..."], "provenance_tier": "retrieved"}], "notes": "..."}

- `nonce` -- copy the value above back, character for character. A reply
  without it is discarded unread.
- `candidates` -- may be an empty list if you genuinely found nothing new.
  **An empty list is a legitimate answer and is better than an invented one.**
- `notes` -- free text: what you looked at, what you were unsure about.
```

### 6.2 `write-cell-test.md` (toàn văn phần luật)

```markdown
# Write one executable test for one exact combination of inputs

## The combination
{{TARGETS}}

Every name/value pair above has to be really established in the running code
before you assert anything: set it, construct it, configure it, or monkeypatch
it. **A test that asserts under default inputs, while merely mentioning these
values in a comment or a test name, is worthless and will be discarded.**

## Where to write it
    {{PROBE_PATH}}

## Rules the file has to obey
- Runnable on its own, from the working directory, with no arguments.
- **Exit non-zero when the behaviour is wrong**, zero when it is right.
  The exit status is the whole answer.
- Assert about real behaviour of the real code -- import it, call it, drive it.
  **Never assert about a value the test itself just computed.**
- Every assertion independent: none may be reachable only if an earlier one
  passed, or one failure hides the others.
- More than one independent assertion, if the behaviour has more than one
  observable consequence. **One assertion that can only ever be true is the
  thing this file exists to avoid.**
- No network. No writing anywhere except the path above.
- If you cannot establish the combination above in the running code, write the
  file, make it exit non-zero, and say exactly which pair you could not
  establish in `notes`. **Never make it pass by widening what it checks.**
```

Prompt còn lại cùng thư mục: `propose-constraint.md`, `write-adversarial.md`, `write-axis-probe.md`, `build-sut.md`, `config-author.md`.

---

## 7. Stop gate — 9 điều kiện (`architecture.md:466`)

> **(0)** `stop_hook_active == True` ⇒ in lý do MỘT lần rồi cho qua — **và khi đi qua bằng cửa này thì ghi record `gate_bypassed` mang lý do, sau đó `report.py` CẤM in RELEASE PASS**. Rồi re-derive và chặn nếu:
> - **(a)** còn ô `unknown` không stub sống trong zone `w ≥ blocking_w`
> - **(b)** `false_high_rate` zone đó vượt `stop-gate.false_high_block`
> - **(c)** defect trong zone chặn không có tham chiếu
> - **(d)** có `unknown`/`stale` không nằm trong **tập khai CHỐT LÚC MỞ RUN** (digest trong `governance.lock`) — *so với tập vừa tự sinh là điều kiện tự thoả mãn chính nó, không bao giờ bắn*
> - **(e)** `verify_chain()` gãy, governance hash lệch, cross-check lệch ĐẾM theo bất kỳ chiều nào, hoặc transcript vắng/không parse được (`witness_unavailable`, **fail-closed**)
> - **(f)** manifest sha256 của `bin/**` lệch
> - **(g)** `axes --check-drift` thấy enum SUT mọc giá trị lưới chưa có
> - **(h)** Class B: mutation-catch của bất biến cấm-tuyệt-đối `< 1.0`, small-scope chưa verify, ô interleaving còn `unknown` sau bão hoà
> - **(i)** tập-ô-bị-chặn **RỖNG**, hoặc `lock/calibration.lock.json` vắng, hoặc một ô `high` trong zone chặn không có `mutation_run` `killed` khớp seed
>
> Zone `w` thấp được phép `unknown` **khi đã khai** — **im lặng mới là vi phạm**.

---

## 8. DEBTS.md — nhật ký sai lầm thật, mỏ vàng để cài lỗi

### 8.1 CON SỐ RỖNG — cùng một số, ba nguyên nhân khác nhau (`O1`)

> **BA con số rỗng LIÊN TIẾP cho cùng một phép đo, mỗi cái rỗng một kiểu:**
> `1.0` (bắt 48/48) — nền là hạt **đã vi phạm sẵn** trên mã lành, oracle nổ dù có cấy hay không;
> `0.0` (bắt 0/48) — nền lành nhưng **một writer chạy tuần tự**, không lỗi nào làm nó va chạm nổi;
> `0.0` lần hai — nền đúng rồi, nhưng **module đã nạp vào `sys.modules`**, sửa tệp trên đĩa KHÔNG đổi mã đang chạy.
> **Lần ba nguy hiểm nhất: `0.0` đọc y hệt *oracle mù hoàn toàn*, sự thật là *lỗi cấy chưa từng chạy một dòng*.**

⇒ Một mutation score phải kèm **bằng chứng rằng mutant thực sự chạy** (`mutant_in_force` + `_mutant_reaches_running_code`).

### 8.2 `rate=1.0` bị đọc ngược (`M1`)

> **⚠ ĐỌC KỸ `rate=1.0`: đây là tỉ lệ CHẤM-CAO-SAI, tức con số TỆ NHẤT có thể, KHÔNG phải "100% bắt được".** Bản ghi gốc: `{"killed": 0, "survived": 2, "rate": 1.0}` và cổng chặn đúng vì lẽ đó. 7 ô còn lại `missing` — *"probe_absent_so_nothing_to_re_run"*.
> Đây là **con số duy nhất nói cả cỗ máy có đáng tin không**. Đo trên cỡ mẫu 2 thì chưa nói được gì.

**→ Đây chính là chỗ Wilson interval phải được ghép vào.**

### 8.3 Lưới an toàn thưa hơn tưởng rất nhiều (`M3`)

> **Bộ bất biến Lớp B chỉ bắt được 1/48 lỗi cấy — tỉ lệ 2%.** `{caught:1, escaped:47, sample_size:48, rate:0.021}`
> **Đây KHÔNG phải lỗi engine — engine đang làm đúng việc của nó: nói cho ta biết lưới an toàn thưa đến mức nào.** … một lượt chạy không tìm ra vi phạm KHÔNG nói hệ đúng, nó nói **cái duy nhất được canh thì không sai**.
> Cấm đóng dòng này bằng cách hạ cỡ mẫu hay đổi nền đo — ba nền SAI đã cho ra `1.0`, `0.0`, `0.0`, mỗi cái đọc như một kết luận.

### 8.4 "Xanh câm" (`B19`) — lớp lỗi lớn nhất

> **Cổng gác "xanh CÂM": vòng lặp không còn gì để duyệt, phép kiểm vẫn ĐẠT.** Đây là dạng hỏng đắt nhất của cả cây: **phép kiểm xanh vì không nhìn thấy gì, không phải vì không có lỗi** — và đọc lại mã KHÔNG tìm ra, vì mã trông hoàn toàn hợp lý.

Quỹ đạo phát hiện: **8 ca → hơn 25 → hơn 90 → hơn 110**. Và:
> **lớp `B19` tái sinh bên trong chính bản vá viết ra để chặn `B19`** — lần thứ ba trong cả đợt, và lần này ở ngay cổng gác cuối.

Cấy lỗi lần 5 vẫn thủng — thêm vòng quét mù **kèm luôn dòng miễn trừ cho chính nó** trong cùng commit ⇒ **ĐI LỌT**. Cái cổng chỉ đổi được **KIỂU HỎNG**: từ *lặng lẽ viết một phép kiểm mù* thành *viết một phép kiểm mù cộng một dòng khai báo điều đó, nằm trong diff* — **hành vi soát được thay vì hành vi vô hình**.

### 8.5 Ước lượng bằng bộ đếm rộng (`B28`)

Ước lượng `~810` → đo thật `76` (**sai ~11 lần**).
> con số **3467 xanh** chứng minh đúng phần `B27` đã cấy. Nó **không** chứng minh 740 ca `other-call`. Đọc "48/48 armed" mà kết luận lớp đã sạch là đọc sai: **91/920 mới là độ phủ thật của các sàn.**

Tự thú: *"riêng đợt này **suy luận về 'hình dạng nào an toàn' đã sai ba lần**"*.

### 8.6 LLM agent cấp NGUYÊN NHÂN thay vì HIỆN TƯỢNG (`B28` lô 3) — cực kỳ liên quan workshop

> **Bài học nặng nhất của lô này — ba lần vá cho MỘT ca:** tác nhân A báo "shim không nạp `governed`", tôi vá theo hai lần, cả hai XANH; lần ba mới chạy `sys.modules` thật ⇒ **`governed: True`, kết luận của tác nhân SAI**. Tác nhân **đo đúng hiện tượng (xanh), chẩn đoán sai nguyên nhân**, và tôi kê đơn theo chẩn đoán thay vì theo phép đo.
> Luật: **báo cáo của tác nhân cấp HIỆN TƯỢNG, không cấp NGUYÊN NHÂN — tự đo lại nguyên nhân trước khi vá.**

### 8.7 Regex trên code luôn trả tập NHỎ HƠN thật (`B26`)

> Cùng bài học ba lần trong đợt này: **khảo sát bằng regex trên mã luôn trả tập NHỎ HƠN thật; dùng AST.**

Ví dụ đo được: `tree.body` không thấy `if True: import yaml` · quét chuỗi liền mạch không thấy `"claude" + " -p"` (CPython gấp lúc biên dịch) · quét theo LOẠI nút AST không thấy `__import__("subprocess")` · glob `*.tmp-*` không thấy tệp thừa đổi đuôi.

Và (`B25`): vòng cấy lỗi đầu chọn dòng theo **văn bản thụt lề** nên trúng dòng trong **docstring** ⇒ báo "vẫn mù" SAI. **Cấy phải nhắm cấu trúc mã, không nhắm chuỗi.**

### 8.8 Ô bất khả thi = điểm mù giả VĨNH VIỄN (`O1`)

> Trục đầu khai `overlapping_reads × single_actor`, không thể tồn tại. Engine báo *chưa chạm, rủi ro TRUNG BÌNH* **mãi mãi** — **nó KHÔNG phân biệt được *bất khả thi* với *chưa ghé***.

`dst-schedule-axes.yaml:20-23`:
> The search reported it unreached with a MEDIUM residual, **correctly and forever**: the engine has no way to know a cell is impossible rather than merely unvisited, so an unreachable cell becomes **a permanent finding that reads like work somebody could do**.

Fix: dự án tự khai qua `impossible_class()`, truyền vào `enumerate_t_wise(exclude=...)` — **khả năng đã có sẵn trong code mà chưa nơi nào truyền vào**.

### 8.9 Cấu hình sai ⇒ grid sập về `unknown` trong im lặng

Ba cách một coverage command "trông hợp lý" làm hỏng tất cả, **cả ba đều silent**:
1. Chỉ collect data mà không sinh report — output dir rỗng
2. Sai format/filename — JSON coverage report không đọc được (chỉ Cobertura XML + LCOV)
3. Không scope vào source của mình:
   > Measured on a real run: every line of the system under test agreed across the two reports, and **the probe script alone — five lines of it — was enough to collapse the whole grid to unknown**. One `--source` flag was the difference between a working measurement and no measurement.

Cùng loại: `project.sut_path` chưa điền ⇒ *"ten real, passing probes whose evidence was all unusable, every cell unknown, and **a report that read as confident**"*.

### 8.10 Nợ chặn còn mở

| ID | Nội dung |
|---|---|
| `O2` | `axes.freeze()` **không pha nào gọi** — mọi lượt D2 thành công dựa vào một lần đóng băng THỦ CÔNG |
| `O3` | Ô được miễn chấm hiện trong sổ nhưng **không cổng nào đọc** — mồ côi ở chiều dữ liệu |
| `B29` | Ghi sổ bằng chứng **phình theo bình phương**: 10.000 record = **36,2 giây**; gấp đôi record ≈ 3× thời gian |
| `B6` | `min_per_zone` không khai khi một vùng bị teo một phần — *"**Lưới tự nhỏ lại trong im lặng** — không ai phá, mẫu số cứ co"* |
| `B16` | `python3 -m <tên>` đi vòng qua cổng lệnh (đo trực tiếp: `rm -rf .tgc/state`→DENY nhưng `python3 -m config`→ALLOW) |
| `M4` | *"Tôi tự nới cái cổng đang bắt chính tôi"* — cần người thứ hai đọc lại |
| `L3` | Quyết định "tự viết mutation thay vì dùng `mutmut`/`cosmic-ray`" **chưa hề được đo** — 0 kết quả khi grep mọi tên công cụ mutation; đang đỡ **932 dòng** code |

---

## 9. Trích dẫn verbatim quan trọng nhất

1. `harness/scripts/project.py:2` — **luật số một**: *"a grid cell's band is DERIVED, never asserted, never model-chosen."*
2. `README.md:86-90` — *"Con số 92% đó **đúng**, và **vô nghĩa** … **Cái lưới chính là mẫu số đó.**"*
3. `rollup.py:3-9` — *"Two numbers that must NEVER merge into one … an average lets one high zone hide a low in a completely different zone."*
4. `score.py:10-18` — *"It is a real Goodhart bug, not a strawman."*
5. `project.py:56-61` — *"a blocking-zone high band simply does not exist as a reachable branch of this function without a killed, seed-anchored, BOUND mutant."*
6. `dst_scheduler.py:3-7` — *"only the hash stream is reproducible ACROSS builds … rather than on a promise."*
7. `DEBTS.md:28` — *"Lần ba nguy hiểm nhất: `0.0` đọc y hệt *oracle mù hoàn toàn*, sự thật là *lỗi cấy chưa từng chạy một dòng*."*
8. `DEBTS.md:89` — *"một lượt chạy không tìm ra vi phạm KHÔNG nói hệ đúng, nó nói *cái duy nhất được canh thì không sai*."*
9. `dst-schedule-axes.yaml:20-23` — *"the engine has no way to know a cell is impossible rather than merely unvisited."*
10. `architecture.md:794-795` — *"Mọi con số trong report hoặc mang một `evidence_id`, hoặc in `UNVERIFIED`. **Không có con số nào được suy ra từ thiện chí.**"*

---

## 10. Hạt nhân tối thiểu để implement lại

Bản gốc: **77.536 dòng Python / 3.133 test** — không thể dạy. Hạt nhân giữ đúng ngữ nghĩa:

```
axes.py        →  freeze axis set từ ref có thật     (~80 dòng)
cells.py       →  enumerate_t_wise + count_t_wise    (~50 dòng, chép gần nguyên)
zones.py       →  predicate first-match-wins + w     (~80 dòng)
score.py       →  V / cost / rho                     (~60 dòng, chép gần nguyên)
axis_search.py →  beam trên lattice + quarantine     (~200 dòng)
project.py     →  bảng 17 hàng → band                (~250 dòng, trái tim)
rollup.py      →  RWC (diagnostic) + min_per_zone    (~120 dòng, chép gần nguyên)
escalate.py    →  hot-axes → hot-triples             (~80 dòng)
calibrate.py   →  seed = sha256(digest || nonce)     (~120 dòng)
mutate.py      →  AST operator swap + re-run probe   (~150 dòng)
```

**Bốn luật phải giữ nếu không muốn dạy sai bản chất:**
1. `source: "projected"` — model không bao giờ ghi band. Không CLI surface nào nhận band.
2. Không bao giờ gộp RWC và min-per-zone thành một scalar.
3. `N/A` chỉ vào qua constraint đã admit; `N/A + executed` ⇒ raise.
4. Mọi con số kèm `evidence_id` hoặc in `UNVERIFIED`.

**Ba chỗ nên THÊM mà bản gốc thiếu** (đều là điểm giảng tốt):
- **Wilson interval** cho `false_high_rate` / mutation catch rate — chính DEBTS đang bị chặn bởi vấn đề Wilson giải (`rate=1.0, n=2`).
- **`impossible_cell()` predicate** truyền vào `enumerate_t_wise(exclude=…)` — bản gốc **có sẵn tham số mà chưa nơi nào dùng**, tạo blindspot vĩnh viễn.
- **Tail-read cho evidence ledger** — `B29` là bug O(n²) rõ ràng, ví dụ hay về *"chi phí đúng đắn cũng phải đo"*.
