# CERTUS — DETAILS: lý giải từng bản vá (lý thuyết → luồng hiện tại → luồng sau fix)

> ⚠️ **INSTRUCTOR-ONLY.** Tài liệu này lộ toàn bộ đáp án: nó nói rõ mỗi lỗ hổng
> nằm ở đâu, biểu hiện thế nào, và bản vá làm gì. Nó nằm trong `docs/solutions/`
> nên **bị `scripts/build_student_repo.py` loại khỏi repo sinh viên**. Chỉ công
> khai SAU workshop.

Tài liệu này là bản dài đi kèm `apply_fixes.py` (SSOT các bản vá) và `patches/`
(cùng nội dung ở dạng unified diff). Với **mỗi** trong 12 lỗ hổng cài cắm, nó
trình bày bốn lớp:

1. **Lý thuyết** — khái niệm AI Product Design đứng sau, kèm link tới nghiên cứu nền.
2. **Luồng hiện tại (buggy)** — code làm gì lúc này, tái hiện ra hậu quả gì, đo ở đâu.
3. **Luồng sau fix** — bản vá đổi gì, và vì sao đổi thế mới đúng.
4. **Cách một LLM thật phơi ra lỗi** — vì bài yêu cầu "tái hiện được bằng LLM thật".

---

## Cách đọc

**Hệ bốn nhãn bằng chứng** (chính là khái niệm #06 mà workshop dạy — dùng luôn ở đây):

| Nhãn | Nghĩa | Ví dụ trong tài liệu này |
|---|---|---|
| `[OBSERVED]` | Đã trực tiếp thấy / chạy ra | "grep đếm 1 lần chuỗi X ở `file:line`" |
| `[DERIVED]` | Suy ra từ bằng chứng khác | "vì regex `{8,}` nên khoá ngắn vẫn khớp" |
| `[PRIOR]` | Kiến thức nền chưa re-check trong repo này | "Wilson interval hẹp dần theo √n" |
| `[ASSUMED]` | Giả định chưa kiểm | (tránh dùng; nếu có sẽ ghi rõ) |

**Neo file:line** ở mọi khẳng định về code. Số dòng theo trạng thái **buggy** (repo
gốc, trước khi áp `apply_fixes.py`). Sau khi áp vá, số dòng sẽ trôi.

**Ba tầng mẫu số độ phủ** (không bao giờ trộn — xem Phần I.2):
`line coverage` · `mutation score` · `grid coverage`.

---

## Phần I — Nền lý thuyết chung

Ba trụ nghiên cứu, mỗi trụ là nguồn của một nhóm lỗ hổng. Bản trong repo (đã tiêu
hoá, sinh viên đọc được ở repo sinh viên) và bản nghiên cứu gốc (instructor):

| Trụ | Bản trong repo | Nghiên cứu gốc (ngoài repo) |
|---|---|---|
| Khoảng tin cậy Wilson cho probe-first | [`docs/research-notes/01-confidence-intervals.md`](../research-notes/01-confidence-intervals.md) | `sdlc-harness/docs/research/methodology/confidence-intervals/confidence-intervals-for-probe-first_en.md` |
| ToT grid coverage (độ phủ theo lưới t-wise) | [`docs/research-notes/02-tot-grid-coverage.md`](../research-notes/02-tot-grid-coverage.md) | `sdlc-harness/docs/research/feature/tot-grid-coverage/` |
| Chuỗi cổng QA (QA gate chain) | [`docs/research-notes/03-qa-gate-chain.md`](../research-notes/03-qa-gate-chain.md) | `sdlc-harness/docs/research/feature/qa-gate-chain/` |
| Tổng hợp ba trụ | [`docs/research-notes/04-synthesis.md`](../research-notes/04-synthesis.md) | — |

> ⚠️ `research-notes/03` và `04` chứa gợi ý cài lỗi của instructor → **cũng bị loại
> khỏi repo sinh viên**; chỉ `01` và `02` (lý thuyết thuần) được ship.

### I.1 — Khoảng tin cậy Wilson, không phải "điểm tự tin"

`[PRIOR]` Một tỉ lệ quan sát được `p̂ = k/n` (vd 18/20 ô grid đã phủ) **không** là
sự thật; nó là một ước lượng có sai số phụ thuộc `n`. Khoảng Wilson cho biết dải
mà tỉ lệ thật rơi vào với độ tin cho trước, và nó **hẹp dần theo √n**. Với `n`
nhỏ, một `p̂ = 0.90` có thể đi kèm khoảng `[0.68, 0.97]` — tức "90%" gần như vô nghĩa.

`[DERIVED]` Hệ quả cho sản phẩm: **mọi con số tỉ lệ phải đi kèm `k`, `n`, và
khoảng**, không được rút gọn thành một `float` trần. Đây là gốc của lỗ hổng **#05**
(một field `confidence: float` trần nuốt mất `n`) và một phần của **#04**.

Bảng `min_n` (note 01): muốn khẳng định "đạt ngưỡng T" ở một mức tin, `n` phải đủ
lớn; gate đọc thẳng bảng này. Đây là cầu nối sang trụ thứ ba (gate chain).

### I.2 — Ba tầng mẫu số: line ≠ mutation ≠ grid

`[PRIOR]` Ba câu hỏi KHÁC NHAU, ba mẫu số KHÁC NHAU, **không được cộng/trộn**:

- **Line coverage** — "bao nhiêu dòng chạy khi test chạy". Rẻ, dễ đạt cao, **mù
  chất lượng**: một test không assert gì vẫn kéo line coverage lên 100%.
- **Mutation score** — "test có BẮT được lỗi không". Gieo đột biến vào code, đếm
  bao nhiêu bị test giết. Đắt, nhưng đo đúng "sức khoẻ" của bộ test.
- **Grid coverage** — "còn GÓC rủi ro nào chưa nhìn". Chiếu không gian tổ hợp
  (feature × layer × lifecycle × risk...) thành lưới t-wise; mỗi ô là một tổ hợp
  cần có ít nhất một test chạm.

`[DERIVED]` Trộn ba tầng là cách "con số đẹp che khoảng mù": lấy trung bình line
90% + grid 40% ra "65%" là một con số **không trả lời câu hỏi nào cả**. Đây là gốc
lỗ hổng **#04** (một hàm `overall_coverage_score()` gộp cả tầng chẩn đoán lẫn tầng
cổng), và tinh thần chung xuyên suốt sản phẩm.

### I.3 — Grid coverage: ô, zone, band, projection

`[PRIOR]/[OBSERVED]` Cơ chế grid trong repo (`src/backend/app/core/grid/`):

- **Cell (ô)** — một tổ hợp trục cụ thể. Số ô = tích cardinalities các trục (t-wise).
- **Band** — trạng thái phủ của ô: `COVERED` / `PARTIAL` / `UNCOVERED` / `N/A`.
  `N/A` = ô **không áp dụng** (tổ hợp vô nghĩa), được **miễn khỏi mẫu số**.
- **Zone** — nhóm ô theo rủi ro; zone rủi ro cao cần ngưỡng phủ cao hơn.
- **Projection** — chiếu kết quả test thật lên lưới để tô band từng ô.

`[DERIVED]` Điểm hiểm: ai được quyền đặt `N/A`? Nếu **bên bị chấm** tự đặt `N/A`
cho ô của mình, nó tự miễn mình khỏi mẫu số — "the graded party emptying the
blocking set". Đây là gốc **#03a** (comment trong file người dùng upload đặt được
band `N/A`) và liên quan **#09** (ai có quyền `config:write`).

### I.4 — Chuỗi cổng QA: fail-closed, không fail-open

`[PRIOR]` Một cổng (gate) quyết định pass/block dựa trên bằng chứng đo được. Luật
xương sống: **thiếu bằng chứng ⇒ BLOCK (fail-closed)**, không phải "cho qua vì
chưa thấy vấn đề" (fail-open). Một cổng fail-open là cổng trang trí.

`[DERIVED]` Gate phải đọc **đúng tầng mẫu số** cho câu hỏi của nó (I.2), với `n`
đủ lớn (I.1). Cổng release yêu cầu **golden 0/12** — repo gốc, cả 12 case FAIL đúng
lý do; áp `apply_fixes.py` → 12/12. Đây là bất biến nghiệm thu của cả sản phẩm.

### I.5 — Deterministic vs heuristic: cái gì dùng code, cái gì dùng LLM

`[PRIOR]` Nguyên tắc phân vai:

- **Việc phải TẤT ĐỊNH** (đếm ô, tính Wilson, đọc coverage, chấm gate) → **CODE**.
  Cùng đầu vào phải ra cùng đầu ra, có thể tái lập, kiểm toán được.
- **Việc DIỄN GIẢI** (giải thích cho người, đề xuất) → **LLM**, nhưng mọi CON SỐ
  trong lời diễn giải phải đến từ tool tất định, không được LLM tự tính.

`[DERIVED]` Vi phạm nguyên tắc này là gốc **#07** (prompt mời LLM "tự tính khi tool
lỗi" + tên tool lệch nên tool luôn lỗi) và **#06** (LLM tự phong nhãn `OBSERVED`
mà không tool nào đứng sau). Ranh giới "chỉ tool mới phong được OBSERVED" là bản
lề: nó biến evidence-based từ khẩu hiệu thành cơ chế cưỡng chế được.

---

## Phần II — Bản đồ 12 lỗ hổng

11 khái niệm, 12 lỗ hổng (khái niệm LLM-injection tách hai nhánh 03a/03b). Cột
"patch" trỏ thư mục trong [`patches/`](../../patches/); cột "luồng" là số mục Phần III.

| # | id (golden) | Khái niệm | Tier | Nhà (home) | patch |
|---|---|---|---|---|---|
| 01 | `01_confabulation` | Anti-confabulation | A | `agent/prompts/analyze.md` | `01-anti-confabulation/` |
| 02 | `02_truncation` | Anti-hallucination | A | `agent/retrieval.py` | `02-anti-hallucination/` |
| 03a | `03a_prompt_injection` | LLM injection — prompt | B | `agent/context.py` + `core/grid/project.py` | `03-injection/` |
| 03b | `03b_exec_injection` | LLM injection — code exec | B | `core/exec/runner.py` | `03-injection/` |
| 04 | `04_rollup_merge` | Coverage: con số nói gì | A | `core/grid/rollup.py` | `04-coverage-meaning/` |
| 05 | `05_confidence_field` | Confidence vs khoảng tin cậy | A | `api/schemas.py` | `05-confidence-interval/` |
| 06 | `06_label_from_tool` | Evidence-based vs probe-first | B | `agent/claims.py` | `06-evidence-probe-first/` |
| 07 | `07_deterministic` | Deterministic vs heuristic | A | `agent/prompts/analyze.md` | `07-deterministic/` |
| 08 | `08_data_policy` | Enterprise & data policy | B | `policy/redaction.py` | `08-data-policy/` |
| 09 | `09_authorization` | Permission & authorization | B | `auth/scopes.py` | `09-authorization/` |
| 10 | `10_persona_leak` | Personalization | B | `agent/persona.py` | `10-personalization/` |
| 11 | `11_tracing` | Observability & tracing | A | `observability/tracing.py` | `11-observability/` |

**Tier A** = nên bắt được trong ~20 phút. **Tier B** = phải thật sự khó, đọc kỹ mới thấy.

**Bề mặt chat** (mới): các bản vá `chat-*` trong `patches/` vá lại 01/06/07 trên
prompt hội thoại `agent/prompts/chat.md`. Lưu ý đo được: **bug 06 và 07 chỉ tái
hiện qua flow `analyze`, KHÔNG qua `chat`** — vì `chat.md` dùng tên tool đúng và
`orchestrator/chat.py` không parse claims. Bề mặt chat chỉ tái hiện **bug 01**.

---

## Phần III — Lý giải từng lỗ hổng

Mỗi mục bốn lớp: **Lý thuyết → Luồng hiện tại (buggy) → Luồng sau fix → LLM phơi lỗi thế nào.**

---

### 01 — Anti-confabulation · tier A · `agent/prompts/analyze.md`

**Lý thuyết.** Confabulation = mô hình lấp khoảng trống kiến thức bằng một câu nghe
hợp lý nhưng bịa. Nguyên tắc: bot QA chỉ được nói những gì có trong knowledge base
được cấp; thiếu thì phải nói thiếu. "Không biết" là một câu trả lời ĐÚNG.

**Luồng hiện tại (buggy).** Prompt hệ thống mở đầu: *"Dựa trên knowledge base VÀ
KINH NGHIỆM CỦA BẠN… một cách HỮU ÍCH NHẤT CÓ THỂ"* (`analyze.md:3-4`). Hai vế này
đóng bẫy: đặt "kinh nghiệm của bạn" ngang KB, rồi ép "hữu ích nhất". KB **cố ý**
không chứa ngưỡng branch coverage nào, cũng không có "mục 4.2" ISO 25010. Khi người
dùng hỏi ngưỡng, mô hình — bị ép phải hữu ích, được phép dùng "kinh nghiệm" — bịa
ra một điều khoản ISO và một con số ngưỡng. Không có lối ra nào khác vì prompt
không cho nó lối nào.

**Luồng sau fix** (`patches/01-anti-confabulation/01.patch`). Prompt đổi thành *"Chỉ
được dùng nội dung trong knowledge base… Không được bổ sung từ trí nhớ của bạn"* +
lối ra tường minh: *"Nếu KB không chứa câu trả lời, hãy nói thẳng: KB hiện tại không
có thông tin về điều này."* Bất biến nghiệm thu (`assert`): prompt **không** còn
`"kinh nghiệm của bạn"` / `"hữu ích nhất có thể"`; **có** một trong `"không có thông
tin" / "tôi không biết"`; câu trả lời không khớp regex bịa ISO 4.2 hay ngưỡng
branch coverage `\d\d%`.

**LLM phơi lỗi thế nào.** Hỏi *"Ngưỡng branch coverage tối thiểu theo ISO 25010 là
bao nhiêu?"* → bản buggy trả một con số + trích "mục 4.2" (bịa, KB không có); bản
fix nói KB không có thông tin. Bề mặt chat tái hiện tương đương (`chat-01.patch`).

---

### 02 — Anti-hallucination · tier A · `agent/retrieval.py`

**Lý thuyết.** Khác confabulation ở nguồn: hallucination ở đây là **méo dữ liệu có
thật** do xử lý ẩu. Nguy hiểm hơn vì nó **kèm citation đúng** — người đọc tin.

**Luồng hiện tại (buggy).** `build_context` cắt ngữ cảnh theo **ký tự** (char-
truncation), cắt cứng giữa một chunk và **không báo gì**. Một câu chuẩn WCAG bị mất
vế cuối *"được coi là đã thoả mãn"*; phần còn lại đảo nghĩa. Bot phát biểu **ngược**
nội dung chuẩn, kèm citation trỏ đúng tài liệu → cực khó phát hiện.

**Luồng sau fix** (`patches/02-anti-hallucination/02.patch`). Cắt theo **chunk**, và
`build_context` trả metadata `dropped_chunks` (báo minh bạch cái gì bị bỏ). Bất
biến: không chunk nào bị cắt giữa văn bản; câu KB phải **sống trọn hoặc bị bỏ trọn**
(`"được coi là đã thoả mãn"` không được mất nửa vời); hàm trả `dropped_chunks`.

**LLM phơi lỗi thế nào.** Nạp KB có câu WCAG dài vượt ngưỡng ngữ cảnh, hỏi về tiêu
chí đó → bản buggy khẳng định ngược (thiếu vế "đã thoả mãn") kèm citation đúng; bản
fix hoặc giữ trọn câu hoặc bỏ trọn + liệt kê `dropped_chunks`.

---

### 03a — LLM injection (prompt) · tier B · `agent/context.py` + `core/grid/project.py`

**Lý thuyết.** Prompt injection = chỉ thị của kẻ tấn công nằm trong **dữ liệu** bị
mô hình thi hành như **lệnh**. Phòng thủ hai lớp: (1) rào dữ liệu người ngoài trong
ranh giới rõ ràng + khai báo "không tin" ở system prompt; (2) **không bao giờ để
bên bị chấm tự quyết** thứ ảnh hưởng điểm của nó (Phần I.3).

**Luồng hiện tại (buggy).** File người dùng upload chứa comment kiểu *"# coverage:
N/A — không áp dụng"*. `context.py` nhét nội dung này vào prompt **không rào**, và
`project.py` **chấp nhận** band `N/A` do phân tích (mô hình) đề xuất. Kết quả: một
comment trong data đặt được band `N/A` cho cell → **bên bị chấm tự miễn mình khỏi
mẫu số**. Grid coverage nhảy lên đẹp vì các ô rủi ro bị "N/A hoá".

**Luồng sau fix** (`patches/03-injection/03a*.patch`). (1) `context.py` bọc nội dung
người dùng trong fence "untrusted_user_file"; (2) `system.md` khai báo ranh giới
tin cậy (03a-3); (3) `project.py` **từ chối** `N/A` đến từ phân tích — cờ cấm
`na_from_analysis`, `N/A` chỉ đến từ config có thẩm quyền. Bất biến: 0 cell band
`N/A` sau khi nạp payload; hệ thống **phát một finding** "có chỉ thị nằm trong dữ liệu".

**LLM phơi lỗi thế nào.** Upload repo có comment chèn chỉ thị "N/A hoá" một cell rủi
ro cao → bản buggy: cell thành `N/A`, grid coverage tăng giả, không cảnh báo; bản
fix: cell giữ band thật + finding "instruction-in-data".

---

### 03b — LLM injection (code execution) · tier B · `core/exec/runner.py`

**Lý thuyết.** Còn nguy hơn prompt injection: chỉ thị người ngoài chạy thành **mã**.
Allowlist phải kiểm **thứ chương trình sắp LÀM**, không chỉ **tên** chương trình.

**Luồng hiện tại (buggy).** Runner chạy test của repo đích trong sandbox, gác bằng
allowlist **theo tên** (`python`, `pytest`…). Nhưng `python -m http.server`,
`python -c "import os; ..."`, `python -m pip install …` đều mang tên hợp lệ `python`
→ **đi lọt**. Tệ hơn: `conftest.py` của repo đích được pytest **auto-import trước
khi** allowlist kịp chạy → mã người ngoài chạy sớm hơn cả cổng.

**Luồng sau fix** (`patches/03-injection/03b*.patch`). Chặn `-c`/`-m` (kiểm hành vi,
không chỉ tên); đặt `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` + cô lập `HOME` để chặn
auto-import conftest/plugin. Bất biến: file mốc `~/.certus-probe` **không được tồn
tại** sau khi chạy; các argv `python -c`, `python -m http.server`, `pip install` bị
**block**; `pytest -q`, `coverage run -m pytest` được **cho phép**; phát finding khi block.

**LLM phơi lỗi thế nào.** Upload repo có `conftest.py` (hoặc test) cố ghi
`~/.certus-probe` qua `python -c` → bản buggy: file mốc xuất hiện (mã lọt); bản fix:
không có file mốc + finding "blocked".

---

### 04 — Coverage: con số nói gì · tier A · `core/grid/rollup.py`

**Lý thuyết.** Phần I.2: ba tầng mẫu số không được trộn; và tầng **chẩn đoán**
(risk-weighted, để con người đọc) khác tầng **cổng** (min-per-zone, để máy chặn).
Gộp chúng thành một scalar là xoá thông tin.

**Luồng hiện tại (buggy).** `rollup.py` có hàm `overall_coverage_score()` gộp
risk-weighted coverage với min-per-zone thành **một số**. Một trung bình cho phép
**một zone tốt che một zone tệ** ở chỗ hoàn toàn khác: hạ một cell trong zone nặng
nhất mà scalar tổng gần như không nhúc nhích → gate không lật, khoảng mù lọt.

**Luồng sau fix** (`patches/04-coverage-meaning/04.patch`). Bỏ hàm gộp; API trả
**cả hai cấu trúc riêng** `risk_weighted` (gắn nhãn *diagnostic*) và `per_zone`.
Bất biến: module **không** phơi scalar gộp (`overall_coverage_score`/`combined_score`
/`total_coverage` bị cấm tên); response có cả `risk_weighted` lẫn `per_zone`;
risk_weighted phải gắn nhãn diagnostic; **hạ một cell ở zone nặng nhất PHẢI lật gate**.

**LLM phơi lỗi thế nào.** Đây là lỗi tầng code, phơi bằng test hơn là hội thoại:
so hai lần chạy khác nhau một cell ở zone nặng → bản buggy scalar không đổi, gate
giữ pass; bản fix per-zone đổi, gate lật.

### 05 — Confidence score vs khoảng tin cậy · tier A · `api/schemas.py`

**Lý thuyết.** Phần I.1: một tỉ lệ `p̂ = k/n` mà không có `n` và khoảng là con số
rỗng. Một field `confidence: float` đơn lẻ nuốt mất `n` — người đọc thấy "100%" mà
không biết nó dựa trên 3 mẫu.

**Luồng hiện tại (buggy).** `schemas.py` có field trần `confidence: float`, và
`pipeline.py` gán `confidence = grid_rate.point` (chính `p̂`). Khoảng Wilson **đã
được tính** ở tầng dưới nhưng bị **bỏ đi** khi serialize. Hậu quả đo được: 3/3 cell
hiển thị `100% / 100%` trong khi Wilson95 với `k=3, n=3` chỉ đảm bảo cận dưới
**≈ 43.9%**. "Tự tin 100%" trên 3 mẫu là dối trá thống kê.

**Luồng sau fix** (`patches/05-confidence-interval/05*.patch`). Bỏ field trần; response
mang `k`, `n`, `interval.lower/upper/method`. Bất biến: **không** còn `confidence:
float` trần; có đủ `k, n, interval.*`; `interval.lower` phải KHÁC `p̂` (với
`k=3,n=3` cận dưới = `0.4385 ± 0.001`); phát cờ `n-too-small` khi `n` nhỏ.

**LLM phơi lỗi thế nào.** Nạp repo mà một cell chỉ có 3 quan sát, hỏi "độ tin cỡ
nào?" → bản buggy nói 100%; bản fix nói `p̂=100%` nhưng khoảng `[43.9%, 100%]`, cờ
`n quá nhỏ`. Đây là cặp bài trùng với #01: một bên bịa dữ liệu, một bên bịa **độ tin**.

---

### 06 — Evidence-based vs probe-first · tier B · `agent/claims.py`

**Lý thuyết.** Phần I.5, bản lề của cả workshop: **chỉ tool (probe tất định) mới
thăng hạng một claim lên `OBSERVED`.** Mô hình nói tự tin hơn không làm claim đúng
hơn. Nhãn phải suy ra từ **bằng chứng đã ghi sổ (ledger)**, không phải từ lời tự khai.

**Luồng hiện tại (buggy).** `parse_claims` dựng `Claim.model_construct(...)` và lấy
thẳng `label = Label(c["label"])` **do LLM trả về**. Mô hình chỉ cần viết
`"label": "OBSERVED"` là claim được phong `OBSERVED` — kể cả khi `evidence_ids`
rỗng, không tool nào đứng sau. `pipeline.py` có một lớp re-validate nhưng **cố ý
không chặn** đúng ca này (chỉ lọc claim dị dạng cấu trúc). Nhãn tin cậy nhất trở
thành thứ dễ giả nhất.

**Luồng sau fix** (`patches/06-evidence-probe-first/06*.patch`). Thêm
`_label_from_evidence`: nhãn **suy ra từ anchors/evidence_ids** (tra ledger), bỏ
qua nhãn LLM tự khai. Bất biến: `parse_claims` **phớt lờ** label do model cấp;
không claim nào là `OBSERVED` nếu không có bằng chứng; model khai `OBSERVED` với
evidence rỗng → **bị hạ xuống `ASSUMED`**.

**LLM phơi lỗi thế nào.** Đây là bug **chỉ tái hiện qua flow `analyze`** (chat không
parse claims). Hỏi một câu mà mô hình thích tự tin trả lời không cần tool → bản
buggy: claim gắn `OBSERVED` dù `evidence_ids=[]`; bản fix: cùng claim thành `ASSUMED`.

---

### 07 — Deterministic vs heuristic · tier A · `agent/prompts/analyze.md`

**Lý thuyết.** Phần I.5: con số phải TẤT ĐỊNH (từ tool), diễn giải mới dùng LLM.
Một prompt cho LLM "tự tính khi tool lỗi" là mời heuristic thay chỗ code — và nếu
tool **luôn** lỗi thì mọi con số đều là bịa.

**Luồng hiện tại (buggy).** Hai vế cộng hưởng: (1) prompt liệt kê tool tên
`count_cells`, nhưng registry đăng ký `count_grid_cells` (`grid_tools.py:58`) → tên
lệch, **tool luôn "không khả dụng"**; (2) prompt tiếp: *"Nếu tool không khả dụng…
bạn có thể tự tính toán… để tránh làm gián đoạn"* (`analyze.md:28-29`). Ghép lại:
tool không bao giờ gọi được → LLM luôn tự tính cell_count → **mẫu số sai, im lặng**
→ mọi tỉ lệ phía sau sai theo, mỗi lần chạy một khác.

**Luồng sau fix** (`patches/07-deterministic/07*.patch`). Sửa tên tool khớp registry
(`count_grid_cells`); đổi prompt thành *"Mọi con số phải đến từ tool; nếu tool lỗi
thì DỪNG và báo lỗi, tuyệt đối không tự tính."* Bất biến: prompt **không** còn "tự
tính"/"để tránh làm gián đoạn"; **có** "dừng lại và báo lỗi"; **mọi tool nêu trong
prompt phải tồn tại trong registry**; 3 lần chạy cho `cell_count` **giống hệt nhau**.

**LLM phơi lỗi thế nào.** Chạy `analyze` cùng một repo 3 lần → bản buggy: `cell_count`
nhảy số mỗi lần (LLM tự đếm khác nhau), không hề báo tool lỗi; bản fix: hoặc con số
tất định giống nhau, hoặc dừng + báo tool lỗi. **Chỉ tái hiện qua `analyze`** (tên
tool ở `chat.md` vốn đã đúng).

### 08 — Enterprise & data policy · tier B · `policy/redaction.py`

**Lý thuyết.** Danh mục chặn (blocklist) trong doanh nghiệp chỉ được **THÊM**, không
được **BỚT**: một config cho phép "override" thay cả danh sách = cho phép ai đó gỡ
lá chắn. Redaction phải vừa theo **mẫu tên** (`*.env`) vừa theo **nội dung** (bắt
`sk_live_…`, private key…).

**Luồng hiện tại (buggy).** Config `blocklist_override` **THAY** cả danh sách chặn
thay vì hợp nhất. Một config gỡ `*.env` khỏi danh sách là làm rỗng phần chặn file
bí mật → `.env` thật (chứa `sk_live_…`) lọt vào prompt/log/cassette. Danh mục đáng
lẽ append-only trở thành replaceable.

**Luồng sau fix** (`patches/08-data-policy/08*.patch`). `blocklist_override` gỡ mẫu
đang bảo vệ → **raise `ConfigError`** (không cho bớt); redaction bổ sung lớp
content-based; ngoại lệ allowlist phải kèm lý do. Bất biến: override gỡ `*.env`
**không có hiệu lực**; mẫu `*.env` phải sống sót; prompt **không** khớp
`sk_live_|BEGIN … PRIVATE KEY|password=|AKIA[0-9A-Z]{16}`; ngoại lệ phải có reason.

**LLM phơi lỗi thế nào.** Nạp repo `payments` có `.env` (khoá GIẢ định-dạng-thật),
cấu hình override gỡ `*.env`, chạy analyze → bản buggy: chuỗi `sk_live_…` xuất hiện
trong prompt/log; bản fix: `ConfigError` hoặc khoá bị che, kèm finding.
*(Ghi chú: repo sinh viên đã rút ngắn body khoá giả để qua GitHub push-protection;
redaction `sk_live_[A-Za-z0-9]{8,}` vẫn khớp — xem `scripts/build_student_repo.py`.)*

---

### 09 — Permission & authorization · tier B · `auth/scopes.py`

**Lý thuyết.** Bên **bị chấm** không được có quyền sửa **tiêu chí chấm**. Đây là
separation-of-duties: `analyst` (người nộp bài để CERTUS chấm) mà có `config:write`
thì tự hạ ngưỡng cho mình pass.

**Luồng hiện tại (buggy).** Role `analyst` có scope `config:write` (`scopes.py`),
sửa được `zones.yaml`. Hạ `blocking_w` của zone = làm rỗng tập chặn → mọi gate pass.
Bên bị chấm cầm bút chấm.

**Luồng sau fix** (`patches/09-authorization/09.patch`). Gỡ `config:write` khỏi
`analyst`; compile zones **raise `EmptyBlockingSetError`** khi tập chặn rỗng; override
floor không lý do bị từ chối; mọi thay đổi config ghi ledger kèm **actor**. Bất
biến: `analyst` **không** có `config:write`; `PUT zones.yaml` với tư cách analyst →
**403**; tập chặn rỗng → raise; đổi config được ghi sổ kèm người thực hiện.

**LLM phơi lỗi thế nào.** Đây là lỗi tầng quyền, phơi bằng request: gọi
`PUT /config/zones.yaml` với token `analyst` → bản buggy: 200 + zone bị sửa; bản
fix: 403. *(Lưu ý: đây là một trong các lỗ hổng từng bị vá NGOÀI Ý MUỐN trong một
phiên trước rồi khôi phục lại đúng chủ đích — xem lịch sử commit.)*

---

### 10 — Personalization · tier B · `agent/persona.py`

**Lý thuyết.** Cá nhân hoá (thói quen test của một người, bài học rút từ từng
project) phải **cô lập theo ngữ cảnh**. Bài học ở project A rò sang project B, hoặc
sang người khác, ở bản SaaS là **sự cố bảo mật phải công bố**.

**Luồng hiện tại (buggy).** `record_lesson` nhận `project_id` rồi **vứt đi** (không
lưu cột); `lessons_for` **không lọc theo `project_id`**. Bài học "hàm apply_discount
thiếu test coupon hết hạn" rút ở project A bị nhét vào prompt khi phân tích project
B của cùng người → rò ngữ cảnh chéo project.

**Luồng sau fix** (`patches/10-personalization/10*.patch`). `record_lesson` lưu
`project_id` (cột NOT NULL); `lessons_for(user, project)` lọc đúng project; tái dùng
chéo project cần **đồng ý tường minh**. Bất biến: ghi ở projA rồi đọc ở projB →
**rỗng** (`[]`); cột `project_id` NOT NULL; reuse chéo cần consent.

**LLM phơi lỗi thế nào.** `record_lesson(u1, projA, …)` rồi `lessons_for(u1, projB)`
→ bản buggy: trả về bài học của projA (rò); bản fix: `[]`. Trong hội thoại: phân
tích projB thấy prompt nhắc tới hàm chỉ tồn tại ở projA = bằng chứng rò sống.

---

### 11 — Observability & tracing · tier A · `observability/tracing.py`

**Lý thuyết.** Một lần phân tích = một cây span **chung một `trace_id`**; đứt
`trace_id` ở đâu là mất dấu ở đó. Log phải mang `trace_id` để nối, và **không được
ghi nguyên payload** (prompt/KB) — chỉ hash + độ dài + token count (đụng cả #08).

**Luồng hiện tại (buggy).** Span của lời gọi LLM tự sinh `trace_id = uuid4().hex`
mới → cây span **đứt đúng chỗ đắt nhất** (lời gọi model). Log format **thiếu**
`trace_id`; `log_llm_call` ghi **nguyên payload** (prompt đầy đủ, kèm bí mật nếu có).

**Luồng sau fix** (`patches/11-observability/11*.patch`). LLM span dùng
`_ensure_trace_id()` (thừa kế trace hiện hành, không tự sinh); `LOG_FORMAT` thêm
`extra[trace_id]` với mặc định `"-"`; `log_llm_call` chỉ ghi `sha256 + length +
token_count`. Bất biến: mọi span trong một lần phân tích chung **đúng 1** `trace_id`;
log format chứa `extra[trace_id]`; log **không** chứa prompt đầy đủ; chỉ ghi
`sha256/length/token_count`.

**LLM phơi lỗi thế nào.** Chạy một lần phân tích, đếm `trace_id` phân biệt trong các
span → bản buggy: >1 (đứt ở LLM span); bản fix: đúng 1. Đồng thời grep log tìm nội
dung prompt → bản buggy có, bản fix chỉ có hash.

---

## Phần IV — Nghiệm thu & cách áp

**Bất biến golden 0/12.** Repo gốc: cả 12 case FAIL đúng lý do (`evals/golden/cases.json`,
mỗi case một `check`). Áp `apply_fixes.py` → 12/12. Không thay đổi nào được hồi sinh
hoặc giết nhầm case nào. Cổng release CI gác đúng bất biến này.

```bash
python docs/solutions/apply_fixes.py --check    # xem chỗ nào CÒN LỖI (0/12)
python docs/solutions/apply_fixes.py            # áp cả 12 → 12/12
python docs/solutions/apply_fixes.py --only 04  # áp một lỗi
```

**Quan hệ với `patches/`.** `patches/**` là **cùng nội dung** apply_fixes ở dạng
unified diff, sinh bằng `docs/solutions/emit_patches.py`, gom theo lỗ hổng. Áp tất
cả (tích luỹ, đúng thứ tự): `bash patches/apply-all.sh`. Đọc một bug: mở
`.patch` tương ứng — diff tự đủ nghĩa. Các bản `chat-*` là **surface** (vá 01/06/07
trên `chat.md`), ngoài mẫu số golden 12.

**Ma trận tái hiện.** Không phải bug nào cũng phơi qua mọi bề mặt:

| Bề mặt | Phơi được |
|---|---|
| `analyze` (single-shot) | tất cả 01–11 |
| `chat` (multiturn tool-loop) | **chỉ 01** (chat.md dùng tên tool đúng + không parse claims) |
| Test/golden | mọi bug tầng code (04, 05, 06, 09, 10, 11, 03b…) |

**Không telegraph.** Không bug nào được đánh dấu trong fixtures/tên file/comment.
Bộ test xanh **kể cả khi** cả 12 lỗi còn nguyên — test xanh ở đây không chứng minh
tính đúng, đó chính là bài học tầng #04/#06.

---

*Tài liệu này là bản dài của `apply_fixes.py`. Khi apply_fixes đổi, cập nhật lại
các mục Phần III tương ứng để số dòng và bất biến khớp.*
