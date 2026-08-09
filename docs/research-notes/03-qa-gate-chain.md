# Research note 03 — QA Gate Chain

**Nguồn:** `/home/hieubt15/Documents/vsf/sdlc-harness/docs/research/feature/qa-gate-chain/` (18 file, 3.919 dòng)
**Nguồn trích kèm:** `harness/data/iso-25010-matrix.yaml`, `docs/product/_refs/frankcode-src/planner-executor/engines/qa/gatesRegistry.ts`

---

## 0. Cảnh báo provenance — đọc trước

Đây **không phải** tài liệu mô tả một hệ thống đang chạy. Đây là **hồ sơ khám nghiệm một dây chuyền gate đã chết**, cộng bản thiết kế lại.

Bài toán `TASK-4417` trong `hypothesis/` là **fiction do model dựng** (`hypothesis/_index.md:1-4`) — dùng làm kịch bản workshop thì tuyệt vời (nó được thiết kế đúng cho việc đó: người hỏi → model sai → bị bắt lỗi → tự thú → sửa), nhưng **đừng trích như case study có thật**.

Mọi **lỗi kỹ thuật** được mô tả thì **đo thật**, có `file:line`, có exit code. Đó mới là nguyên liệu.

**Wilson interval KHÔNG tồn tại trong corpus này.** `grep -rin "wilson|confidence interval|khoảng tin cậy|binomial"` trên toàn `qa-gate-chain/` → **0 hit, exit 1**. Mở rộng ra toàn bộ `docs/research/feature/` (9 cụm) → **0 file**.

**"Coverage" ở đây KHÔNG phải line/branch coverage** — nó là **coverage matrix theo chiều chất lượng** (ISO 25010 / OWASP / WCAG). Và chính nó cảnh báo: line coverage 100% vẫn mù với chiều chất lượng không có hàng trong ma trận.

---

## 1. Gate là gì

Định nghĩa lặp đồng nhất ở 4 file (`mission.md:698`, `corpus-map.md:147`, `architecture.md:547`, `decisions.md:351`):

> **gate / cổng** | Chốt kiểm **có quyền chặn**, không chỉ nhắc nhở.

Hai định nghĩa bổ trợ quyết định tất cả:

> **oracle** | Thứ phân xử đúng-sai **bằng máy**. Không có oracle thì không cưỡng chế được, chỉ nhắc được.
>
> **engine / bộ máy** | Thứ **thực thi** một phép kiểm và làm nó hoá đỏ. **Kiểu dữ liệu, tài liệu, tên hàm đều không phải engine.**

### 1.1 Chuỗi 5 gate

`gatesRegistry.ts:22-27`:
```ts
export type GateName =
  | 'requirements' | 'design' | 'grid' | 'execution' | 'outcome'
```

Dây chuyền và artifact chảy qua (`mission.md:122-135`):
```
plan-comprehensiveness
  → requirements-testability            (Gate 1: requirements)
    → iso25010-coverage
      → [ risk-based-testing ‖ security-owasp ‖ a11y-wcag ]   (Gate 2: design)
        → mece-test-design / regression-sentinel
          → grid-review                 (Gate 2a: grid)
            → bàn giao Executor
              → rule-based-verification trên PR diff   (Gate 3: execution)

plan PR → GateVerdict{requirements} → GateVerdict{design} → GridReviewVerdict
        → PR diff → GateVerdict{execution}
```

Hai đặc điểm hình dạng dễ bỏ sót:
- Gate 2 **rẽ ba song song** (risk ‖ security ‖ a11y) → thiết kế phải mô tả **luật hợp nhất ba verdict thành một**, không phải chỉ nối mũi tên.
- `mece-test-design` chạy ở **hai gate khác nhau** — nhánh lặp thứ hai của cả đồ thị.

### 1.2 Mỗi gate kiểm gì

| GateName | Thẻ nạp vào | Kiểm gì |
|---|---|---|
| `requirements` | plan-comprehensiveness · requirements-testability · adversarial-review | Kế hoạch đủ mặt không; **tiêu chí nghiệm thu có kiểm được bằng máy không** |
| `design` | iso25010-coverage · risk-based-testing · security-owasp · a11y-wcag · mece-test-design (lần 1) | Ma trận phủ 8 đặc tính; độ sâu theo rủi ro; lớp lỗ hổng; **MECE + 10 đường bắt buộc** |
| `grid` | — (cụm C sở hữu) | Gate 2a |
| `execution` | rule-based-verification · mece-test-design (lần 2) · regression-sentinel | **Quét luật tất định trên PR diff**; đối chiếu diff với ma trận đã duyệt |
| `outcome` | outcome-qasuite.ts | Cron 24h/7d/30d |

### 1.3 Tiêu chí PASS/FAIL

⚠ **Trong hệ tham chiếu, KHÔNG gate nào có tiêu chí được thi hành** — cả 5 đều là stub trả `pass` cứng. Dưới đây là tiêu chí **trên giấy** (mức `retrieved`):

| Gate | FAIL khi |
|---|---|
| `requirements` | `verification_type ∈ {test, rule, manual}`; nhánh `test` phải có `binary_check=true`; nhánh `rule` phải có `rules[]` với `scope/match/assert/severity`; nhánh `manual` phải **nêu tên người kiểm** |
| `design` | (a) số đặc tính `covered` < **risk floor** (`critical:8, high:6, medium:4, low:2`); (b) `silent_na: reject` — ô không có quyết định là **defect**, không phải "đã phủ"; (c) **10 đường bắt buộc**, mỗi đường phải có một dòng test **hoặc** một câu `N/A because {{reason}}` — *"Paths present but silently uncovered = matrix rejected at Design Gate"* |
| `execution` | Diff phải **khớp ma trận hàng-đối-hàng**; mỗi vi phạm bắt buộc có `rule_id/severity/file/line/finding` |
| `regression-sentinel` | *"No sentinel, no closed post-mortem"* |

### 1.4 Định nghĩa ĐO ĐƯỢC của "gate thật" — `architecture.md:295-329`

> Một cái cổng chỉ là cổng khi **chứng minh được HAI điều bằng máy**:
>
> 1. **Ba ca, một đường mã.** Ca **vi phạm** ⇒ `fail`; ca **không vi phạm** ⇒ `pass`; ca **biên** (số đo bằng đúng ngưỡng) ⇒ kết quả do khoá `gate.compare_op` quyết định. **Dấu so sánh phải nằm trong hợp đồng**, không được để ngầm.
> 2. **Đếm nơi gọi.** Hàm chấm phải có **≥ 1 nơi gọi ngoài chính tệp định nghĩa** và **ngoài cây bài kiểm**. **0 nơi gọi ⇒ ĐỎ.** Phép đếm phải phát ra **mẫu số** `symbols_scanned` cùng tử số `orphans`; `symbols_scanned == 0` ⇒ ĐỎ.
> 3. **Đối chứng dương bắt buộc.** Phép đếm cho **kết quả rỗng** trong hai hoàn cảnh khác hẳn nhau: *"quét sạch, không có hàm mồ côi"* và *"quét trượt, không bắt được gì"*. Không có đối chứng ⇒ **số 0 không được đọc thành phán quyết**.

Ví von trung tâm (`architecture.md:299-300`):
> Một cái barie chỉ là barie nếu nó **từng hạ xuống**. Barie luôn giơ lên, dù sơn đẹp và có biển tên, là **một cái cột trang trí**.

---

## 2. Gate ở đâu trong SDLC

Tài liệu **không** map theo trục `pre-commit / push / PR / nightly / release`. Nó map theo **hai trục khác**:

### Trục 1 — thời điểm trong vòng đời task

| Giai đoạn | Gate |
|---|---|
| Kế hoạch còn là **chữ**, chưa có dòng code nào | Gate 1 `requirements`, Gate 2 `design`, Gate 2a `grid` |
| **Sau khi code đã commit** — chạy trên **PR diff** | Gate 3 `execution` |
| **Cron sau khi ship** (24h / 7d / 30d) | Gate 5 `outcome` |

Phân biệt tinh tế nhất (`_raw/methodology-survey.md:99-103`):
> **Cái phân biệt hai lần gọi:** không phải phạm vi (macro/micro), mà là **THỜI ĐIỂM TRONG VÒNG ĐỜI TASK** — trước khi code tồn tại (lần 1, chấm THIẾT KẾ) so với sau khi code đã commit (lần 2, chấm CODE có khớp bản thiết kế đã duyệt hay không).

### Trục 2 — "bề mặt chặn": D1 vs D2

Trục này trả lời **"một verdict `fail` DỪNG ĐƯỢC Ở ĐÂU"**:

| | Là gì |
|---|---|
| **D1** "trong phiên" | hook chặn ngay bên trong một phiên đang sống (`PreToolUse`/`Stop`) |
| **D2** "ngoài phiên" | chương trình tự chạy, không người trông; chặn giữa hai phase |
| **substrate** | sổ bằng chứng, danh mục, luật — cả D1 lẫn D2 cùng đọc |

**Kết quả probe thật** (`architecture.md:422-428`, mốc `933850cf`, `executed`):

| Tầng | Kết quả |
|---|---|
| Trong phiên | **CÓ bề mặt chặn đã nối, đang sống** — hook đọc YAML rồi `sys.exit(2)`; có nơi gọi trong `hook-dispatch.yaml:97` |
| Trong phiên, cổng dựa artifact | **CÓ** — verdict `APPROVED` bị **từ chối** khi phép kiểm phụ trả mã ≠ 0 |
| **Ngoài phiên** | **CÓ HÀM CHẤM, KHÔNG CÓ NƠI GỌI SẢN PHẨM** ⇒ verdict chỉ là **`được khuyến nghị`**. `grep -rn "build_grid("` → 6 kết quả, ngoài `tests/` chỉ còn **chính dòng định nghĩa** |

**Dịch sang workshop:** D1 ≈ pre-commit / hook cục bộ; D2 ≈ CI job / nightly. Tài liệu chứng minh: **hook cục bộ đã nối và chặn thật; tầng CI/tự động có hàm chấm nhưng KHÔNG AI GỌI.** Đó chính là "không có gate" trong đời thực.

---

## 3. Cấu trúc dữ liệu của gate

### 3.1 Schema gốc — trích nguyên văn (`gatesRegistry.ts:29-83`)

```ts
export type GateVerdictLevel =
  | 'approve' | 'block' | 'request-revision' | 'pass' | 'fail'

export type FindingSeverity = 'info' | 'warn' | 'error'

export interface Finding {
  severity: FindingSeverity
  code: string
  message: string
  citedField?: string
}

export interface GateVerdict {
  gate: GateName
  verdict: GateVerdictLevel
  findings: Finding[]
  citedFields: string[]
  advisorConsulted: boolean
  confidence?: number
  /** True when the gate intentionally skipped (e.g. grid on LOW band). */
  skipped?: boolean
  gridArtifacts?: GridArtifacts
}

export interface GateRunnerOptions {
  plan?: PlanFrontmatter
  task?: TaskFrontmatter
  prDiff?: string
  gridSidecar?: GridFrontmatter
  outcomeWindow?: OutcomeWindowLabel
  adapters: ToolAdapters
}
```

⚠ **Tài liệu CẤM bê thẳng schema này** — `GateVerdictLevel` **trộn hai hệ verdict** (hệ review kế hoạch `approve/block/request-revision` với hệ thi hành `pass/fail`) ⇒ bẫy trùng-từ-khác-nghĩa (`DD-9`).

### 3.2 Schema của bản thiết kế mới (`architecture.md:129-134`)

> **Hai từ vựng lõi duy nhất được phép cứng:**
> 1. `verdict ∈ {pass, fail}` — **một** hệ phán quyết duy nhất. Lõi **cấm** trộn thêm hệ thứ hai kiểu *duyệt / chặn / đòi sửa*.
> 2. `evidence_tier ∈ {executed, retrieved, derived}` — ba mức bằng chứng. **Không có mức thứ tư kiểu "nói suông"**; một khẳng định không đo được thì mang nhãn `UNVERIFIED`, và **`UNVERIFIED` là một phán quyết hợp lệ**.

Hợp đồng gate: **Vào** = tạo tác của một chặng. **Ra** = `verdict ∈ {pass, fail}` kèm `findings[]`, **mỗi mục có `file` + `line`**.

### 3.3 Bảng khai báo config (`architecture.md:114-124`)

| Loại tên riêng | Khoá config | Bộ kiểm hình dạng | Hỏng thì sao |
|---|---|---|---|
| mã đơn vị công việc | `unit.id` · `unit.id_pattern` | khác rỗng **và** khớp pattern do dự án khai | dừng, nêu tên khoá, exit ≠ 0 |
| tên chiều chất lượng | `catalogue.rows[].id` | khác rỗng, **duy nhất trong tờ** | dừng, nêu **cả hai** dòng trùng |
| tên chuẩn ngoài | `catalogue.source_id/source_version/source_ref/snapshot_path` | **cả bốn** phải có; `snapshot_path` phải trỏ tệp **có thật trong cây** | dừng, nêu khoá thiếu |
| tầng đếm | `catalogue.depth` · `depth_vocab` | `depth` phải thuộc `depth_vocab` khai ngay trong tờ | dừng |
| người chịu trách nhiệm | `unit.owner_ref` | chuỗi mờ — lõi **không bao giờ diễn giải** nội dung | chỉ kiểm có mặt |
| công cụ dò | `detector.cmd` · `required_placeholders` | `cmd` phải chứa **đủ** mọi ô trống đã khai | dừng, nêu ô trống thiếu |
| chặng trong dây chuyền | `stage.id` (từ `stage.vocab` của dự án) | phải thuộc `vocab`; **lõi không mang danh sách chặng nào** | dừng |
| chính sách N/A | `catalogue.na_policy` · `na_policy_source` · `source_kind` | `na_policy ∈ {require_reason, allow_silent}`; `source_kind ∈ {external, house}` | dừng |
| sàn phủ theo rủi ro | `floor.<risk_band>` (**tệp RIÊNG**) | số nguyên > 0; ghi đè phải kèm `reason:` khác rỗng | thiếu ⇒ dừng; ghi đè thiếu `reason` ⇒ **từ chối, luật không đổi** |

**Ba tệp, ba chủ sở hữu:**

| Tệp | Ai sở hữu | Ghi đè |
|---|---|---|
| `catalogue.<source_id>.yaml` | cấu hình của harness | dự án chỉ được **THÊM** hàng, không được **BỚT** |
| `floor.yaml` | dự án đích | được **cả hai chiều**, bắt buộc kèm `reason:` |
| `snapshot/<source_id>@<source_version>` | harness, chỉ-đọc sau khi ghim | không |

### 3.4 YAML thật đang chạy — hiện trường của lỗi trung tâm

`harness/data/iso-25010-matrix.yaml:1-35`:
```yaml
silent_na: reject   # a cell with no covered/N-A-reason/gap decision is a defect, not "covered"

risk_floors:
  critical: 8
  high: 6
  medium: 4
  low: 2

characteristics:
  - id: functional_suitability
    name: "Functional Suitability"
    sub_properties: [completeness, correctness, appropriateness]
    typical_layers: [unit, integration]
  ...
  - id: usability
    name: "Usability"
    sub_properties: [learnability, operability, accessibility, ui_aesthetics]
    typical_layers: [uat, manual]
```

**`accessibility` chỉ là một `sub_property` ở dòng 34 — nó không bao giờ có hàng riêng để mà bỏ trống.**

**Khuôn ba vế bắt buộc trên MỌI tệp config của gate** (`architecture.md:246-249`):
(i) **một chỗ ở duy nhất** · (ii) **suy ra từ đâu** · (iii) **điều kiện phải xem lại**.
Vế (iii) là thứ thường thiếu, và thiếu nó thì *"một con số sẽ hoá thành hằng số vĩnh viễn"*.

Khuôn tốt được khen (`scope-split.yaml:1-8`):
> *"Scope-split threshold (S4). SINGLE home for the cell-count cap — **no default in code**. … **Re-review this value if** the budget row or per-cell cost estimate changes."*

---

## 4. Fail-closed vs fail-open

### 4.1 Định nghĩa & lập trường

> **dừng-khi-nghi-ngờ** (fail-closed) | Gặp cấu hình thiếu hoặc hỏng thì **dừng và báo lỗi**, không âm thầm rơi về một giá trị mặc định.

`architecture.md:159-165`:
> Mọi bộ kiểm chạy theo kiểu **dừng-khi-nghi-ngờ**: gặp cấu hình thiếu hoặc sai khuôn thì **báo lỗi nêu đích danh tên khoá và mã thoát ≠ 0**, tuyệt đối không âm thầm lấy một giá trị mặc định.

Bảng §2.1 có **9/9 dòng đều là "dừng"**. Không dòng nào ghi "cảnh báo rồi chạy tiếp".

Fail-closed áp cả cho **mẫu số rỗng** (luật `L11`): *"mọi công cụ quét phải phát ra **mẫu số cùng tử số**; **`N == 0` là ĐỎ**, không phải xanh"*. Và: *"không có gì để soi là **một sự cố cấu hình**, không phải một kết quả tốt"*.

### 4.2 Bốn dạng fail-open đã đo được

| Dạng | Hiện trường |
|---|---|
| Gate luôn trả `pass` | 5/5 handler là `stub()` |
| Luật có, detector `null` ⇒ chỉ còn advisory | **143/145** dòng `detector: null` |
| `severity: info` ⇒ không hoá đỏ | 2 luật a11y, cả hai `info` + `detector: null` |
| Warning sinh ra nhưng **0 consumer** | `override_warnings` chỉ 2 hit, **cả hai trong chính file sinh nó** |

**Phân biệt sắc nhất của cả bộ tài liệu** (`_raw/deepdive.md:47-52`, `:257-264`) — hai lớp phải tách:

> - **Lớp REFUSE (luật chặn) — CÓ THẬT, không điều kiện.** Cái thực sự chặn là **cấu trúc, không phải cảnh báo**: một override bị từ chối thì nhánh `continue` chạy TRƯỚC khi field được gán — tức luật gốc **không đổi bất kể có ai đọc `warnings` hay không**.
> - **Lớp "LOUD" (cảnh báo hiển thị) — KHÔNG được nối đi đâu cả.** docstring tự khai *"is LOUD (it surfaces a warning)"* **chỉ đúng ở nghĩa "hàm trả về một list string"**.

⇒ **Một gate an toàn phải chặn bằng cấu trúc control-flow** (không gán / `continue` / `sys.exit(2)`), **không** bằng việc trả về cảnh báo rồi hy vọng ai đó đọc.

### 4.3 Abstain — ba dạng hợp lệ

**(a) `UNVERIFIED`** — *"Phán quyết hợp lệ: chưa đo được. **Không** được đọc thành 'không có'."*

**(b) `skipped`** — gate cố ý bỏ qua theo band rủi ro.

**(c) N/A có chính sách** — phát hiện đắt nhất (`DD-4`). **Hai chuẩn quốc tế nói NGƯỢC NHAU:**

| Chuẩn | Khi tiêu chí không áp dụng |
|---|---|
| **OWASP ASVS** | **bắt buộc khai lý do** — *"must clearly indicate in any report a reason for non-applicability"* |
| **WCAG 2.2** | **cho phép im lặng** — *"if there is no content to which a success criterion applies, the success criterion is satisfied"* |
| **ISO/IEC 25010** | **không có khái niệm này** — là taxonomy, không phải quy trình chứng nhận (`UNVERIFIED` — iso.org trả HTTP 403) |

⇒ `na_policy` khai **theo TỪNG danh mục**, không phải hằng số toàn hệ, **cộng** `source_kind ∈ {external, house}` để chống lỗi *"khai **chính sách của nhà** như thể là **yêu cầu của chuẩn ngoài**"*.

**Test chứng minh chính sách thật sự được đọc:** chạy bộ chấm **hai lần trên cùng một ô**, chỉ đổi `na_policy`. Hai phán quyết **khác nhau ⇒ XANH; giống nhau ⇒ ĐỎ**.

### 4.4 Bất đối xứng ghi đè (`DD-3`)

| | Ghi đè | Lý do |
|---|---|---|
| **Danh mục** | chỉ **THÊM**, không **BỚT** | *"ai muốn né một chiều chỉ cần xoá hàng đó khỏi tờ — và **mọi phép kiểm sẽ báo xanh**"* |
| **Sàn (floor)** | **cả hai chiều**, bắt buộc `reason:` | sàn là **chính sách**, không phải sự thật. Thiếu `reason` ⇒ **TỪ CHỐI, luật giữ nguyên** |

---

## 5. Gate dùng bằng chứng gì

### 5.1 Thang 3 mức + 1

| Mức | Nghĩa | Dùng làm kết luận? |
|---|---|---|
| `executed` | đã chạy lệnh thật, có exit code | ✅ |
| `retrieved` | đã lấy được văn bản gốc, đọc trực tiếp | ✅ |
| `derived` | suy ra từ đọc, có nói rõ suy từ đâu | ✅ có điều kiện |
| `asserted` | **nói suông** | ❌ **CẤM tuyệt đối** |
| `UNVERIFIED` | chưa đo được | ✅ verdict **hợp lệ** |

### 5.2 Hình thức bằng chứng gate phải sinh ra

1. `findings[]` mỗi mục có **`file` + `line`**
2. **Mẫu số kèm tử số** — *"Đã soi 40 thứ, thấy 0 lỗi"* vs *"0 lỗi"* trơ trọi (không phân biệt được với *"chưa soi cái nào"*)
3. **Đối chứng dương** — chạy đúng lệnh đó lên một thứ **chắc chắn phải có kết quả** trước khi tin một kết quả rỗng
4. **Content hash** chống sửa lén giữa hai gate (sha256-12hex trên nội dung chuẩn hoá, gấp cả file con vào hash)
5. **Sổ bằng chứng append-only 5 trường**: `claim · command · exit code · output · verdict`; verdict ∈ `{executed-pass, executed-fail, UNVERIFIED}`

---

## 6. Anti-pattern "KHÔNG CÓ GATE" — mỏ vàng để cài lỗi

Tài liệu đếm **6 ca của cùng một bệnh trên 3 hệ độc lập**. Câu chẩn đoán trung tâm:

> Ba hệ, năm ca, **một bệnh**: *có luật, không có người thi hành*.

### A. Gate hình thức — có tên, có type, luôn PASS

| | Dấu hiệu |
|---|---|
| A1 | **Handler là `stub()` trả `verdict: 'pass'` cứng.** `grep -c "stub("` → **5** |
| A2 | **Chuỗi `'fail'` chỉ tồn tại ở khai báo TYPE và COMMENT — không nhánh mã nào trả về nó.** Tập verdict đến được có đúng **1 phần tử** |
| A3 | **Type/interface đầy đủ, chi tiết, đẹp — mà rỗng.** *"một cái cổng **có kiểu dữ liệu đầy đủ** vẫn có thể rỗng — **kiểu dữ liệu không phải engine**"* |
| A4 | **Comment hứa hẹn một thư mục KHÔNG TỒN TẠI.** `registerGate()` khai *"used by `src/qa/gates/*.ts`"* — `find -type d -name gates` → **rỗng** |
| A5 | **File tự khai mình là bản khung "sẽ làm sau".** *"Subsequent slices (W-QA-3 → W-QA-7) replace stubs with real implementations"* — slice đó không bao giờ tới |

### B. Gate mồ côi — code có, 0 caller

| | Dấu hiệu |
|---|---|
| B1 | **`runGate(` có 0 nơi gọi** trong toàn bộ 36 file `.ts` — chỉ khớp dòng định nghĩa |
| B2 | **`registerGate` có 0 nơi đăng ký handler thật** |
| B3 | **DI để `None` ở MỌI call-site sản phẩm.** `driver.py:99` gán `self._critic = critic`; nhưng `critic=None` tại **cả bốn** entrypoint |
| B4 | **1616 dòng detector + 395 dòng critic + 269 test — không đường chạy thật nào đi qua** |
| B5 | **Caller duy nhất nằm ngoài đường chạy thật.** File tự khai *"Manual harness (not collected by pytest — no test_ prefix)"* |
| B6 | **Đã port script chặn sang, có test, nhưng 0 hook nào gọi.** *"Nó được **định tuyến bằng văn xuôi**: nếu model không tự gọi thì **không có gì hoá đỏ**"* |
| B7 | **Hàm chấm có nhánh `BLOCK` nhưng 0 caller sản phẩm** |

### C. Gate "cửa mở, chưa ai bước vào"

| | Dấu hiệu |
|---|---|
| C1 | **Sổ registry RỖNG.** Luật *"No sentinel, no closed post-mortem"* + CLI **11.878 byte** — mà nội dung sổ là `sentinels: []` (**14 byte**) |
| C2 | **143/145 luật mang `detector: null`** — luật tồn tại, **máy dò thì không** |
| C3 | **Luật đúng chủ đề nhưng `severity: info` + `detector: null`** — *"chúng là lời khuyên, không phải cổng"* |
| C4 | **20 bộ luật schema đẹp, artifact bắt buộc `file`+`line` — mà 99% luật không có oracle.** *"verdict cuối vẫn do model đọc mà ra"* |

> **T-D4 — hai dạng hỏng, CẤM gộp:**
> **(a) không ai gọi** — code tồn tại, 0 caller ⇒ oracle là **phép đo caller/reachability**
> **(b) gọi được nhưng chưa ai gọi** — cửa mở, sổ rỗng ⇒ oracle là **phép đo mức độ sử dụng thật**
> *"Hai dạng cần hai phép đo khác nhau; gộp một là báo xanh cho cả hai."*

### D. Gate bị bypass / vô hiệu âm thầm

| | Dấu hiệu |
|---|---|
| D1 | **Gate chỉ kiểm SỰ CÓ MẶT của artifact, không đọc NỘI DUNG.** Tự khai *"the coverage-grid VERDICT is never read here"* |
| D2 | **Warning sinh ra nhưng 0 consumer** |
| D3 | **Config được phép BỚT hàng khỏi danh mục** ⇒ né một chiều bằng cách xoá hàng, mọi phép kiểm xanh |
| D4 | **Ghi đè hạ chuẩn không cần lý do** |
| D5 | **Rule-id mới "né" floor bằng scope chồng lấn + posture yếu hơn** |

### E. Test giả — oracle kiểm CHỮ thay vì kiểm HÀNH VI

| | Dấu hiệu |
|---|---|
| E1 | **Test duy nhất của cả tầng QA: 87 dòng, 14 lời gọi `toContain(`, 0 lần chạm mã.** `expect(FRANKODE_QA_AGENT).toContain('Tier 1')` — không import gì, không gọi `runGate`, không kiểm verdict nào. *"87 dòng kiểm chính tả của một file văn xuôi"* |
| E2 | **Bản vá cũng mắc đúng bệnh:** `expect(coverageMatrix).toContain('accessibility')` — *"Nó xanh vĩnh viễn ngay khi ai đó gõ thêm dòng `accessibility: covered`, kể cả khi nút Tải CSV vẫn là một `<div>` không nhãn"* |
| E3 | **Test xanh KHÔNG phải bằng chứng đã cắm** — *"test gọi được cả code đã chết"*. Phép kiểm đúng là **reachability**, không phải in-degree |
| E4 | **Thiếu ca biên, dấu so sánh để ngầm** — gate không khai `compare_op` |
| E5 | **Thiếu cặp đột biến** — không có phép thử *"làm hỏng hành vi mà giữ nguyên chữ ⇒ phải đỏ"* |

### F. Blind spot cấu trúc

| | Dấu hiệu |
|---|---|
| F1 | **Hạt đo sai tầng.** Sàn đếm **đặc tính** (8), lỗi rơi ở **sub-property** (29) |
| F2 | **Anti-silent-check chỉ bắt ô TRỐNG, không bắt HÀNG KHÔNG TỒN TẠI.** *"Đây không phải luật bị vi phạm. Đây là luật **không được gọi tới**"* |
| F3 | **Danh sách "10 đường bắt buộc" không có đường a11y** — đội liệt kê đủ 10/10 mà không nghĩa vụ nào nhắc tới accessibility |
| F4 | **Danh mục không khai `depth`** ⇒ không ai biết nó mù ở đâu |
| F5 | **Không có nhịp riêng chất vấn chính danh sách** — *"danh sách cố định **luôn** mù với thứ ngoài danh sách"* |

### G. Catalogue chết

| | Dấu hiệu |
|---|---|
| G1 | **0 script đọc tờ danh mục.** `grep -rn "iso-25010-matrix" harness/scripts/` → **0 file**. *"người thi hành duy nhất của nó là **một model đọc văn xuôi**. Không có `import yaml` nào ở đầu kia"* |
| G2 | **Catalogue nằm sai lớp kiến trúc** — bảng OWASP sống trong văn xuôi cho model, không phải config script đọc được |
| G3 | **Không ghi phiên bản nguồn ngoài** ⇒ đổi bản danh mục giữa hai lượt chạy làm **mọi số đo phủ mất khả năng so sánh** |
| G4 | **Không có snapshot trong cây** ⇒ nhịp chất vấn không có gì để đối chiếu |
| G5 | **Catalogue gộp chung file với floor** ⇒ sàn rủi ro hoá **hằng số của harness** |
| G6 | **Thiếu vế (c) "điều kiện phải xem lại"** ⇒ *"sẽ hoá hằng số vĩnh viễn"* |

### H. Phép đo tự lừa — họ "kết quả rỗng"

Ví von: *"Bốn cách để một cái cân báo '0 kg' mà bạn **không được tin**: cân sai chỗ · cân chưa bật · cân hỏng nên luôn báo 0 · có hai vật nặng bằng nhau đặt hai đầu triệt tiêu nhau."*

| Luật | Kiểu rỗng | Anti-pattern |
|---|---|---|
| `L6` | rỗng vì **quét sai phạm vi** | Lấy `grep` 0-hit làm **tiêu chí** thay vì đối chứng |
| `L11` | rỗng vì **chưa quét gì** | Báo "0 lỗi" không kèm **mẫu số**; `N == 0` đọc thành xanh |
| `L12` | rỗng vì **lệnh vốn không bắt được gì** | Không có **đối chứng dương** |
| `L10` | **không rỗng** nhưng do **lỗi triệt tiêu nhau** | Kiểm theo **SỐ** thay vì theo **TÊN** — *"thừa một chỗ, thiếu một chỗ, tổng vẫn khớp"* |
| `L8` | danh sách cố định **mù với thứ ngoài danh sách** | Không khai `depth` |
| `L9` | kết luận tựa lên **một con số tự chọn** | Ngưỡng bịa không kiểm độ nhạy |

Bẫy shell rất đáng cài: **`grep … | head` che mất mã thoát thật** — `echo $?` sau ống dẫn đọc mã thoát của lệnh **cuối** (`head`, luôn `0`), không phải của `grep`.

### I. Verdict / từ vựng hỏng

- **I1** Trộn hai hệ verdict trong một type ⇒ bẫy trùng-từ-khác-nghĩa
- **I2** Khai **chính sách của nhà** như thể là **yêu cầu chuẩn ngoài** — `silent_na: reject` áp lên cả WCAG (nơi im lặng hợp lệ) và ISO 25010 (nơi chuẩn gốc không có khái niệm này), **không chỗ nào ghi đó là lựa chọn riêng**
- **I3** Đổi tên khi port gây va chạm từ vựng

### J. Báo cáo giả

- **J1** *"5/5 gate PASS"* đến từ **một bảng markdown đội tự gõ**, không từ một lời gọi hàm
- **J2** **Đọc một HẰNG SỐ thành một PHÁN QUYẾT** — thấy chuỗi `verdict: 'pass'` và báo cáo như kết quả chấm; chữ `stub` cách đúng **hai dòng**
- **J3** Nhầm *"tồn tại artifact"* với *"nội dung artifact là phán quyết máy sinh"*
- **J4** *"Có tên trong danh sách"* bị đọc thành *"có người thi hành"*

### K. Bản vá không chạm lỗ — phần hay nhất để dạy

| Đơn thuốc nghe rất đúng | Vì sao trượt |
|---|---|
| Nối `axe-core` vào Gate 2 | đăng ký handler vào registry mà **`runGate` 0 caller** ⇒ **bản vá vô hình đúng như lỗ hổng** |
| Nâng sàn HIGH từ 6/8 → 8/8 | sàn đếm **đặc tính**, lỗi ở **sub-property** ⇒ **"Lỗ không hẹp đi một milimet nào"** |
| Bắt buộc thẻ `a11y-wcag` | thẻ đó `RE:none` ⇒ **thêm một tờ giấy, không thêm một cái cổng** |

> *"Vặn một nút không nằm trên đường của lỗi thì vặn hết cỡ cũng vô ích."*

### L. Repo không kiểm chứng được

**Không có `package.json` nào trong toàn corpus** ⇒ không cài được deps, không dựng được, không chạy được, **không có cả tầng CI để tra chéo**. Mọi claim về runtime trần **`derived` vĩnh viễn**.

### M. BẢNG TỔNG — 8 lớp bảo vệ cùng mù một hạt

| Lớp bảo vệ đội tin cậy | Trạng thái thật |
|---|---|
| 5 gate QA chấm điểm | cả 5 là hàm giả trả `pass` cứng; `runGate` 0 nơi gọi; `src/qa/gates/` không tồn tại |
| Sàn phủ 6/8 theo rủi ro | đếm **đặc tính**, mù với **sub-property** |
| `silent_na: reject` | chỉ bắt ô **trống**; không bắt ô **không tồn tại** |
| 10 đường bắt buộc của ma trận MECE | trong 10 đường **không có** đường a11y |
| Thẻ `a11y-wcag` nạp vào Gate 2 | bảng của chính nó gắn `RE:none` |
| Luật a11y bên harness | đúng 2 luật, cả hai `severity: info` + `detector: null` |
| Tờ danh mục ISO 25010 | 0 script đọc; consumer duy nhất là văn xuôi dặn model tự đọc |
| Bài test của tầng mã QA | 87 dòng, 14 `toContain(`, 0 lần chạm mã |

> **Đọc một câu:** dây chuyền có **8 lớp**, và **8 lớp cùng mù ở đúng một hạt**. **Không lớp nào hỏng.** Chúng chỉ **không nhìn vào chỗ đó**, và **không lớp nào có nhiệm vụ báo rằng mình không nhìn.**

### N. Gợi ý cài cắm trực tiếp

| Anti-pattern | Cách cài |
|---|---|
| A1+A2 | `def check_security(diff): return {"verdict": "pass"}` — `"fail"` chỉ có trong type hint / docstring |
| B1 | Viết đủ `run_gate()` có logic thật, nhưng **không import ở đâu ngoài test** |
| B3 | `Pipeline(critic=None)` ở mọi entrypoint sản phẩm, `critic=RealCritic()` chỉ trong `conftest.py` |
| C1 | `regression-sentinel.yaml` chứa đúng `sentinels: []` + CLI đăng ký 300 dòng |
| C2 | `rules.yaml` 145 luật, 143 luật `detector: null` |
| D1 | CI step chỉ kiểm `os.path.exists("coverage.json")`, không parse nội dung |
| D2 | Hàm trả `(result, warnings)`; caller chỉ dùng `result[0]` |
| E1 | Test file toàn `assert "accessibility" in open("README.md").read()` |
| F1 | Coverage matrix 8 hàng "characteristic", lỗi thật ở sub-property không có hàng |
| G1 | `quality-catalogue.yaml` đẹp, đủ comment nguồn — `grep -r catalogue src/` → 0 hit |
| H (L11) | Linter log `"0 issues found"` khi glob pattern sai và quét 0 file |
| I1 | Enum verdict trộn `APPROVED/REJECTED/NEEDS_WORK` với `PASS/FAIL` |
| J1 | `QA_REPORT.md` viết tay "5/5 gates PASS" trong khi CI log không có dòng nào của gate |

---

## 7. DEBTS.md

**35 dòng nhưng nặng.** Định nghĩa:
> **Đây KHÔNG phải backlog.** Backlog là "đáng làm lúc nào đó". Sổ này là **nợ chặn**: không hợp nhất cụm này vào cụm khác khi còn một dòng chưa đóng.
> **Đóng một dòng = đổi trạng thái + trỏ bằng chứng. KHÔNG xoá dòng.** Xoá là mất lịch sử vì sao nó từng chặn.

**Chỉ có ĐÚNG MỘT dòng nợ, và nó nặng nhất có thể:**

| Việc | Vì sao chặn | Trạng thái |
|---|---|---|
| **Thiết kế chưa được cắm vào** — cụm kết thúc ở wave `build-design`, sản phẩm là `architecture.md`. **0 dòng code, 0 ổ cắm** | *"một cơ chế không được cắm thì **không phân biệt được với một cơ chế không tồn tại**"* | **`chặn`** |

**Bài học meta đắt nhất:** cụm này viết **3.900 dòng phân tích về "code không có ai gọi"**, rồi kết thúc với **`0 dòng code, 0 ổ cắm`**. Nó tự dính chính cái bệnh nó đi chữa. → Ví dụ hoàn hảo: **tài liệu chi tiết không phải là cơ chế**.

**Luật bất biến `NNR`:**
- `NNR-1` — code viết ra luôn được cắm vào, **không mồ côi**
- `NNR-3` — **không có bước "merge sau"**; *"Ổ cắm TRƯỚC, engine SAU — slice đầu thêm ổ cắm, test ĐỎ, rồi mới xây"*
- *"**CẤM đặt việc đấu nối thành một bước riêng ở cuối lộ trình.** 'Merge sau' là nửa đắt kinh điển — đo trên 3/3 hệ, nửa đắt luôn bị bỏ lại."*

**Luật trạng thái:** *"**Không slice nào được đánh `done` bằng lời khai** — chỉ bằng bản ghi `executed-pass`. Slice không để lại bằng chứng chạy được ⇒ ghi **`done-có-khuyết-tật`** và **nêu đích danh khuyết tật**."* — 4/9 slice mang nhãn đó.

---

## 8. Trích dẫn verbatim quan trọng nhất

1. `goals/mission.md:74-78` — *"**Bộ máy cưỡng chế là vỏ rỗng — đã đo, không phải phỏng đoán.** Năm cổng đều là hàm giả trả `pass` cứng, và **không một dòng mã nào gọi chúng**. Thư mục `src/qa/gates/` mà chính file đó hứa hẹn **không tồn tại**."*
2. `goals/mission.md:220-222` — *"Ba hệ, năm ca, **một bệnh**: *có luật, không có người thi hành*."*
3. `goals/mission.md:84-87` — **rubric chấm**: *"mọi cơ chế đều phải trả lời được ba câu — ***ai gọi nó · ở dòng nào · cái gì hoá đỏ nếu không ai gọi***. Thiếu câu ba thì cơ chế đó chỉ được *khuyến nghị*, chưa được *cưỡng chế*, và hai thứ đó khác nhau về bản chất."*
4. `gatesRegistry.ts:94-108` — hiện trường:
   ```ts
   const stub = (gate: GateName): GateHandler => async () => ({
     gate, verdict: 'pass', findings: [], citedFields: [], advisorConsulted: false,
   })
   const handlers: Record<GateName, GateHandler> = {
     requirements: stub('requirements'), design: stub('design'), grid: stub('grid'),
     execution: stub('execution'), outcome: stub('outcome'),
   }
   ```
5. `hypothesis/turn-3.md:41-45` — *"**Không một nhánh mã nào trả về `'fail'`.** Tức trong mã **không tồn tại đường đi nào dẫn tới chữ 'trượt'**. Một cái cổng mà tập giá trị trả về khả dĩ chỉ có đúng một phần tử thì nó không phải cổng — **nó là một cái ống**."*
6. `architecture.md:299-300` — *"Một cái barie chỉ là barie nếu nó **từng hạ xuống**. Barie luôn giơ lên, dù sơn đẹp và có biển tên, là một cái cột trang trí."*
7. `hypothesis/turn-5.md:100-104` — *"`accessibility` chưa bao giờ có một ô. Không có ô thì không có ô trống. Không có ô trống thì luật không có gì để bắt. **Đây không phải luật bị vi phạm. Đây là luật không được gọi tới.**"*
8. `hypothesis/turn-6.md:227-230` — *"dây chuyền có **8 lớp**, và **8 lớp cùng mù ở đúng một hạt**. Không lớp nào hỏng. Chúng chỉ **không nhìn vào chỗ đó**, và **không lớp nào có nhiệm vụ báo rằng mình không nhìn**."*
9. `hypothesis/turn-6.md:167-175` — *"Nó đỏ khi **chữ biến mất**. Nó xanh vĩnh viễn ngay khi ai đó gõ thêm dòng `accessibility: covered` vào ma trận — kể cả khi nút Tải CSV vẫn là một `<div>` không nhãn. Nó không chạm một dòng mã sản phẩm nào."*
10. `hypothesis/turn-4.md:59-63` — **chẩn đoán gốc**: *"Cái làm tôi trượt cả bốn lần là cùng một thói quen: **tôi lấy văn xuôi làm bằng chứng cho mã**. Thẻ phương pháp mô tả một cơ chế rất chi tiết, rất tự tin, có cả downstream, có cả ngưỡng — và tôi đọc **sự chi tiết** đó thành **sự tồn tại**."*
