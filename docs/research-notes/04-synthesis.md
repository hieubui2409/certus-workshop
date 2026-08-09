# Research note 04 — Tổng hợp: ghép ba cây thành một

> **Nhãn bằng chứng của chính tài liệu này.** Note 01/02/03 là `[OBSERVED]` — đọc trực tiếp từ file, có `file:line`. Note 04 này phần lớn là `[DERIVED]` — suy ra từ ba note kia bằng một cơ chế được phát biểu rõ. Chỗ nào là lựa chọn thiết kế chưa có bằng chứng, tôi ghi `[ASSUMED]`.

---

## 1. Phát hiện quan trọng nhất: ba cây KHÔNG nối với nhau

`[OBSERVED]` — hai lần grep độc lập, hai agent khác nhau:

| Tìm gì | Ở đâu | Kết quả |
|---|---|---|
| `wilson\|binomial\|clopper\|rule of three` | `tot-grid-coverage/` | **0 hit** |
| `wilson\|confidence interval\|khoảng tin cậy\|binomial` | `qa-gate-chain/` | **0 hit, exit 1** |
| cross-reference giữa `methodology/confidence-intervals/` và `feature/tot-grid-coverage/` | cả hai chiều | **0** |

Ba tài liệu là **ba cây độc lập**. Yêu cầu của bạn — *"mọi nhận định trong bài đều cần được đo cái này"* — **không phải việc chép lại một liên kết đã có, mà là tạo ra nó.**

Đây là tin tốt cho workshop: phần giá trị nhất không phải phần đọc tài liệu, mà là phần ghép.

---

## 2. Ba cây nói gì, và chỗ hở của mỗi cây

`[DERIVED]` — từ note 01/02/03.

| Cây | Câu hỏi nó trả lời | Chỗ hở |
|---|---|---|
| **Wilson CI** | *"Con số này chắc tới đâu?"* | Không nói **đo cái gì**. Không có khái niệm mẫu số của không gian rủi ro. |
| **ToT grid** | *"Còn góc rủi ro nào chưa ai nhìn không?"* | Có mẫu số nhưng **không có thống kê**. `false_high_rate = 1.0` trên `n=2` được ghi thẳng vào DEBTS như một nợ chặn. |
| **QA gate chain** | *"Ai có quyền chặn, và chặn bằng gì?"* | Có cơ chế chặn nhưng **không có số để chặn theo**. Ngưỡng đều là *"con số tự chọn"* mà chính luật `L9` của nó cấm. |

**Mỗi cây thiếu đúng thứ hai cây kia có.**

---

## 3. Ba mối nối — chỗ Wilson thực sự cắm vào

`[DERIVED]`. Cả hai agent, đọc hai tài liệu khác nhau, độc lập chỉ về cùng một chỗ.

### Nối 1 — `false_high_rate` của calibration ← Wilson

`[OBSERVED]` từ note 02 §8.2, DEBTS `M1`:
```
{"killed": 0, "survived": 2, "rate": 1.0}
→ cổng chặn: "measured false-high rate 1.0 exceeds stop-gate.false_high_block=0.15"
→ DEBTS tự ghi: "Đo trên cỡ mẫu 2 thì chưa nói được gì."
```

`[OBSERVED]` — đã chạy `scratchpad/w.py`, implementation cross-check khớp regression anchor của tài liệu (`wilson(8,10) == (0.490162, 0.943318)`, khớp tới 6 chữ số). Với `k=2, n=2` (2 survived trên 2 mẫu):
- point estimate `1.0` → *"100% chấm cao sai"*
- Wilson95 → `[0.3424, 1.0000]` → *"tỉ lệ chấm-cao-sai nằm đâu đó giữa 34% và 100%"*

Cả hai đều chặn (vì lower bound `0.3424 > 0.15`), **nhưng chúng nói hai điều khác nhau**, và điều thứ hai đúng.

Và chiều ngược lại quan trọng hơn: nếu `{"killed": 2, "survived": 0}` → `rate = 0.0` → **PASS**. Wilson95 cho `0/2` là `[0.0000, 0.6576]` → **false-high rate có thể tới 65,8%**, hơn **4 lần** ngưỡng `0.15`. **Point estimate cho PASS, interval cho FAIL.** Đây là ca dạy học đắt nhất của toàn bộ workshop.

> **Ghi chú quy trình — chính tôi đã vi phạm luật này khi viết bản nháp.** Ba con số trên ban đầu tôi *nội suy* từ bảng trong tài liệu thay vì chạy công thức: viết `0.2924` (thật là `0.3424`) và `0.4392` (thật là `0.4385`). Đó đúng là ca `[ASSUMED]` được viết bằng ngữ pháp của `[OBSERVED]` — *"a hallucination wearing OBSERVED grammar"* (note 01 §3). Bảng `min_n` và bảng all-pass thì khớp tuyệt đối vì chúng được **chép**, không **đoán**. Giữ lại ghi chú này làm ví dụ mở màn cho buổi học.

Áp bảng min_n (note 01 §4.4): để lower bound của *"tỉ lệ chấm-cao-sai ≤ 0.15"* thật sự đứng vững, cần `n ≥ 35` cho T=0.90 all-pass. **`n=2` không thể kết luận gì.**

### Nối 2 — grid coverage ← Wilson theo từng zone

`[OBSERVED]` note 02 §3.2: hai con số `RWC` (diagnostic) và `min_per_zone` (gate), cấm gộp.

`[DERIVED]` — cả hai đều là **tỉ lệ trên mẫu nhỏ** và hiện đang được báo cáo trần:
- `RWC` là trung bình có trọng số → không phải binomial thuần → **không áp Wilson trực tiếp được**. `[ASSUMED]` Cách đúng: báo cáo `cells_scored / cells_total` kèm Wilson, tách khỏi giá trị RWC.
- `min_per_zone` là **min**, không phải rate → cũng không áp Wilson trực tiếp.
- **Chỗ áp được thật sự:** tỉ lệ cell đạt `high` **trong một zone**, với `n = số cell trong zone đó`. Một zone có 3 cell, cả 3 `high` → Wilson lower bound `0.4385` (`[OBSERVED]`, đã chạy) → **zone đó chỉ đảm bảo ≥43,9% đạt chuẩn**, không phải 100%.

Điều này nối thẳng vào cảnh báo cluster của note 01 §B2: cell trong cùng một zone **không độc lập** (chúng chia sẻ axes, chia sẻ code path). ⇒ phải dùng `n_eff = n/deff`, và với K < 10 zone thì route = **`cluster-floor`**. `[DERIVED]` Đa số grid trong workshop sẽ có K < 10 ⇒ **route `cluster-floor` là mặc định thực tế**, và điều đó phải hiện ra trên UI.

### Nối 3 — gate threshold ← Wilson lower bound

`[OBSERVED]` note 03: luật `L9` — *"kết luận tựa lên **một con số tự chọn** ⇒ con số tự chọn phải **kiểm độ nhạy** hoặc **khai thẳng là minh hoạ**"*. Và `E4`: *"noise band bằng hằng số bịa (`rel_band = 0.05`) — cùng bệnh với default ICC 0.3"*.

`[DERIVED]` — Wilson chính là "kiểm độ nhạy" mà `L9` đòi. Quy tắc ghép:

> **Gate so `threshold` với `wilson_lower_bound(k, n)`, không bao giờ với `k/n`.**
> Và gate phải in ra `n`. `n` không đủ để đạt threshold ở mọi kịch bản ⇒ verdict là `UNVERIFIED`, không phải `pass`.

Bảng min_n của note 01 trở thành **bảng tra cho gate design**: muốn gate ở T=0.90 thì golden set phải có ≥35 case; T=0.95 → ≥73. `[DERIVED]` Một gate đặt threshold 0.95 trên 20 case là **gate không bao giờ pass được về mặt toán học** — và đó là một lỗi cài cắm rất đẹp.

---

## 4. Bảng hợp nhất từ vựng — ba cây dùng ba hệ chữ khác nhau

`[OBSERVED]` cả ba cột. `[DERIVED]` phần ánh xạ.

| Khái niệm | Wilson CI doc | ToT grid | QA gate chain |
|---|---|---|---|
| Mức bằng chứng | `OBSERVED / DERIVED / PRIOR / ASSUMED` | `executed / retrieved / derived / asserted` | `executed / retrieved / derived` + `UNVERIFIED` |
| "Chưa đo được" | `[ASSUMED: judge uncalibrated]` + dừng | `unknown` band | `UNVERIFIED` (verdict **hợp lệ**) |
| Phán quyết | lower bound vs threshold | `stop_gate` 9 điều kiện | `verdict ∈ {pass, fail}` |
| Cấm tuyệt đối | tự nâng nhãn lên OBSERVED | model ghi band | `asserted` làm kết luận |

**Xung đột phải giải:** cây Wilson có **4 nhãn**, hai cây kia có **3 tier + UNVERIFIED**. `[ASSUMED]` Quyết định cho workshop: dùng **4 nhãn của Wilson doc** làm chuẩn (vì nó là canonical home, `verification-mechanism.md:23-50`), và ánh xạ `UNVERIFIED` ≡ trạng thái *"không đủ tư cách mang bất kỳ nhãn nào"* — tức một nhãn thứ năm ở tầng meta, không cùng trục.

---

## 5. Ba luật chung xuất hiện ở CẢ BA cây

`[DERIVED]` — đây là phần đắt nhất, vì ba tài liệu độc lập hội tụ về cùng ba luật.

### Luật 1 — Mẫu số phải hiện ra, và mẫu số rỗng là ĐỎ

| Cây | Cách phát biểu |
|---|---|
| Wilson | *"n thật là bao nhiêu? Đếm independent item, không phải log line."* · `n=0 → (0.0, 1.0)` |
| Grid | *"`value` is None when every cell was excluded — reporting 0.0 there would misrepresent 'no data' as 'measured and zero'"* |
| Gate | luật `L11`: *"mọi công cụ quét phải phát ra **mẫu số cùng tử số**; **`N == 0` là ĐỎ**"* |

### Luật 2 — Con số không có neo thì không tồn tại

| Cây | Cách phát biểu |
|---|---|
| Wilson | *"Must be anchored: SHA, `file:line`, hoặc real command output. Không anchor → `UNVERIFIABLE`."* |
| Grid | *"Mọi con số trong report hoặc mang một `evidence_id`, hoặc in `UNVERIFIED`. **Không có con số nào được suy ra từ thiện chí.**"* |
| Gate | *"Downstream rejects UNVERIFIABLE — gate coi claim không anchor **như không tồn tại**."* |

### Luật 3 — Người bị chấm không được tự chấm

| Cây | Cách phát biểu |
|---|---|
| Wilson | *"Self-report does not self-approve"* · judge phải calibrate trên bộ do người chấm |
| Grid | *"a grid cell's band is **DERIVED, never asserted, never model-chosen**"* · seed sinh sau khi đóng sổ ledger |
| Gate | luật `B18`: *"the graded party must not be able to empty the blocking set"* · `M4`: *"Tôi tự nới cái cổng đang bắt chính tôi"* |

`[DERIVED]` **Ba luật này là xương sống của workshop.** Mọi lỗi cài cắm nên vi phạm ít nhất một trong ba — như vậy sinh viên học được một khung tư duy chứ không phải 11 mẹo rời rạc.

---

## 6. Điều chỉnh phạm vi so với đề bài ban đầu

`[DERIVED]` — cần nói rõ để không dạy sai.

Đề bài viết *"phát hiện độ phủ test"*, nghiêng về **line coverage**. Nhưng cả ba tài liệu đều nói line coverage là tầng thấp nhất:

- Grid: *"92% đó **đúng**, và **vô nghĩa**: nó là 92% của 6 tình huống, không phải của 24."*
- Gate: coverage ở đây là **ma trận chiều chất lượng**, và *"line coverage 100% vẫn mù với chiều chất lượng không có hàng trong ma trận"*.

⇒ Sản phẩm workshop phải hiển thị **ba tầng mẫu số cạnh nhau**, để sinh viên thấy chúng không thay thế nhau:

```
tầng 1  line coverage      "bao nhiêu dòng đã chạy"          ← quen thuộc, dễ đạt 90%
tầng 2  mutation score     "test có bắt được lỗi không"       ← mẫu số vẫn là dòng đã chạm
tầng 3  grid coverage      "còn góc rủi ro nào chưa ai nhìn"  ← mẫu số là KHÔNG GIAN RỦI RO
        + Wilson trên cả ba  "mỗi con số trên kia chắc tới đâu"
```

Bài học một câu: **ba con số này có thể lần lượt là 94%, 88%, và 3/17 cell — và cả ba đều đúng.**

---

## 7. Bốn hằng số bịa mà cả ba cây đều cảnh báo

`[OBSERVED]` — dùng làm checklist cài lỗi.

| Hằng số | Cây nào cảnh báo | Câu cảnh báo |
|---|---|---|
| `ICC = 0.3` mặc định | Wilson | *"'safe' depends on the very thing you do not know. **No default constant is safe.**"* |
| `rel_band = 0.05` | Wilson | *"Why 5%? Nothing in the data says so."* |
| prior weight table `0.5/0.2/0.1/0` | Wilson (tự thú) | *"It occupies exactly the position that 'default ICC = 0.3' held before being refuted."* |
| mọi `floor.*` | Gate (`L9`) | *"Kết luận chỉ đúng với đúng một bộ số thì đó **không phải kết luận, đó là một minh hoạ**."* |

`[DERIVED]` ⇒ Trong sản phẩm, **mọi ngưỡng phải sống trong config có ba vế** (chỗ ở duy nhất · suy ra từ đâu · điều kiện phải xem lại), và **cấm hằng số mặc định trong code**. Một hằng số ngưỡng nằm trong code là một lỗi cài cắm hợp lệ và rất khó thấy.

---

## 8. Bốn dấu hiệu cargo cult — dùng làm tiêu chí nghiệm thu ngược

`[OBSERVED]` note 01 §F1. Nếu sản phẩm workshop có bất kỳ dấu hiệu nào sau đây thì **chính nó đã rơi vào bẫy nó đi dạy**:

1. Report có interval nhưng **không bao giờ nói `n` từ đâu ra**
2. **Chưa ai từng thấy** một `saturated` interval hay `route = cluster-floor`
3. **MỌI** judge đều "ok" — chưa judge nào bị reject
4. Không có metadata về tuning rounds hay candidates đã thử

`[DERIVED]` ⇒ Sản phẩm phải **cố tình** cho sinh viên thấy đủ bốn thứ đó trong buổi học. Cụ thể: repo mẫu phải có ít nhất một zone rơi `cluster-floor`, một interval `saturated`, và một judge bị `rejected`.

Phòng thủ duy nhất được tài liệu công nhận:
> *"A silent number is easy to ignore. A line reading `WARNING: judge biased toward passing` is not."*

⇒ `[DERIVED]` UI không được chỉ hiển thị số. Mỗi số phải kèm được/không-được-tin và **lý do**.

---

## 9. Chốt lại: câu chuyện một dòng của workshop

`[DERIVED]`

> Sinh viên upload code lên một con bot. Bot bảo *"độ phủ 94%, tin cậy 100%"*.
> Đến cuối buổi, họ chứng minh được rằng câu đó **sai ở bốn tầng khác nhau** — và con bot, thứ đang đi chấm điểm code của họ, **vi phạm đúng mọi nguyên tắc nó in ra màn hình**.

Bốn tầng đó chính là bốn thứ ba tài liệu nói, cộng phần ghép:
1. `94%` không có mẫu số của không gian rủi ro (grid)
2. `100%` là point estimate trên `n` nhỏ (Wilson)
3. Không gate nào thực sự chặn được (gate chain)
4. Và bot tự chấm chính mình (luật 3, cả ba cây)
