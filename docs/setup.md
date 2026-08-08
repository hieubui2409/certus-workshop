# Cài đặt

Mục tiêu: chạy được CERTUS trên máy bạn trong ~20 phút. Nếu quá 40 phút mà chưa xong, dừng lại và điền lỗi vào Form 2 — chúng tôi sẽ hỗ trợ trước buổi học.

## Yêu cầu

| | Phiên bản | Kiểm tra |
|---|---|---|
| Python | **3.11 · 3.12 · 3.13** (KHÔNG dùng 3.14) | `python3 --version` |
| Node.js | 18 trở lên | `node --version` |
| Git | bất kỳ | `git --version` |

Không cần Docker. Không cần API key.

> **Vì sao chặn Python 3.14.** `scipy==1.15.0` chỉ phát hành bản dựng sẵn (wheel)
> tới `cp313`. Cài trên 3.14 thì `pip` không tìm được wheel nên quay sang **biên
> dịch scipy từ mã nguồn** — việc đó cần một trình biên dịch C/Fortran, và trên
> Windows sạch nó dừng ở `ERROR: Compiler cl cannot compile programs`. Ở buổi
> chạy thử đã có người mất cả buổi tối ở đúng chỗ này rồi không hoàn thành được.
>
> Version bị ghim cứng có chủ đích: cả lớp phải ra **cùng một con số** thì mới so
> bài với nhau được. Nới `scipy` là đổi con số Wilson của mọi người.
>
> Máy đang có 3.14? Cài thêm 3.12 rồi trỏ venv vào đúng nó — không cần gỡ 3.14:
>
> ```powershell
> # Windows (winget) — sau đó dựng venv BẰNG 3.12
> winget install Python.Python.3.12
> py -3.12 -m venv .venv
> ```
>
> ```bash
> # macOS / Linux
> python3.12 -m venv .venv
> ```

## Bước 1 — Lấy mã nguồn

```bash
git clone <LINK_REPO>
cd ai-product-design-workshop
```

## Bước 2 — Backend

```bash
cd src/backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Bước này tải khoảng 200 MB (`scipy`, `statsmodels`, `numpy`). Mạng chậm thì đây là chỗ lâu nhất.

## Bước 3 — Kiểm tra môi trường

```bash
python -m certus doctor
```

Lệnh này in ra đúng cái gì thiếu. **Dán nguyên văn output của nó vào Form 2 câu A5**, kể cả khi nó báo lỗi.

## Bước 4 — Chạy backend

```bash
uvicorn app.main:app --reload --port 8000
```

Mở http://localhost:8000/docs — thấy trang API là được.

## Bước 5 — Frontend

Mở terminal **thứ hai**:

```bash
cd src/frontend
npm install
npm run dev
```

Mở http://localhost:5173.

## Bước 6 — Chạy thử

```bash
# terminal thứ ba, nhớ activate venv
cd src/backend && source .venv/bin/activate
python -m certus analyze ../../fixtures/targets/shopcart
```

Nếu ra một bảng kết quả thì bạn đã sẵn sàng.

---

## Chế độ LLM

Mặc định `CERTUS_LLM_MODE=mock` — dùng bản ghi có sẵn, **không cần API key**, và cả lớp thấy cùng một kết quả.

Ai có API key và muốn chạy thật:

```bash
export CERTUS_LLM_MODE=live
export CERTUS_ANTHROPIC_API_KEY=sk-ant-...
```

Không bắt buộc. Trong buổi học chỉ dùng ở phần demo trên sân khấu.

### Chạy live bằng gói Claude qua `ccs` + `cliproxy` (không cần API key trả tiền)

Nếu bạn đã có **gói đăng ký Claude** (Pro/Max) và dùng Claude Code, bạn có thể chạy
CERTUS ở chế độ `live` qua **cliproxy** — một proxy cục bộ bắc cầu SDK Anthropic sang
gói của bạn, KHÔNG tốn API key tính tiền. `ccs` là công cụ quản lý proxy đó.

1. Cài `ccs` (theo hướng dẫn của công cụ) rồi bật proxy cục bộ — nó lắng nghe ở
   `:8317`:

   ```bash
   ccs local          # để nguyên terminal này chạy
   ```

2. Terminal khác, nạp biến môi trường proxy rồi trỏ CERTUS vào:

   ```bash
   eval "$(ccs env local)"                       # cấp token + base URL của proxy
   export ANTHROPIC_BASE_URL=http://localhost:8317   # xem lưu ý (1) bên dưới
   export CERTUS_LLM_MODE=live
   export CERTUS_MODEL=claude-haiku-4-5           # xem lưu ý (2) bên dưới
   uvicorn app.main:app --reload --port 8000
   ```

   Kiểm tra nhanh không cần backend: `python -m certus analyze
   ../../fixtures/targets/shopcart` — ra bảng là proxy đã thông.

**Lưu ý — hai chỗ hay vấp (đã kiểm chứng thực tế):**

1. **Dùng `localhost`, đừng `127.0.0.1`.** Proxy thường chỉ lắng nghe trên IPv6
   (`[::1]`), nên `http://127.0.0.1:8317` sẽ báo *connection refused* còn
   `http://localhost:8317` (hoặc `http://[::1]:8317`) thì thông. `ccs env local` có
   thể tự đặt `127.0.0.1` — cứ export đè lại như trên.
2. **Chọn tên model "trần", tránh biến thể có hậu tố `[1m]`.** `claude-haiku-4-5`
   và `claude-opus-5` chạy tốt; biến thể cache như `claude-opus-5[1m]` có thể làm
   proxy **treo** (request không bao giờ trả về). Haiku rẻ + nhanh, hợp để thử;
   Opus mạnh hơn cho phần diễn giải nhưng tốn hơn.

Chế độ này hoàn toàn tùy chọn — mock vẫn là mặc định và đủ cho mọi bài trên lớp.
Repo mẫu (shopcart/ledger/payments) khoá trục cố định nên kết quả tất định; chỉ khi
bạn **tải repo của mình** lên thì mới bắt buộc qua bước HITL chọn trục.

---

## Lỗi thường gặp

**`pip install` treo ở scipy/numpy**
Mạng chậm. Thử `pip install -r requirements.txt --timeout 120`. Vẫn không được thì dùng mirror trong nước:
```bash
pip install -r requirements.txt -i https://pypi.org/simple --retries 5
```

**`ModuleNotFoundError: No module named 'app'`**
Bạn đang không ở `src/backend`. Mọi lệnh Python phải chạy từ đó.

**`.venv\Scripts\activate` bị Windows chặn**
PowerShell với quyền admin:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**`npm install` lỗi peer dependency**
```bash
npm install --legacy-peer-deps
```

**Cổng 8000 hoặc 5173 đã bị chiếm**
```bash
uvicorn app.main:app --port 8001
npm run dev -- --port 5174
```
Nếu đổi cổng backend, sửa `src/frontend/.env` -> `VITE_API_URL=http://localhost:8001`.

**Xem giao diện mà chưa chạy được backend**
```bash
cd src/frontend && VITE_USE_MOCK=1 npm run dev
```
Frontend có sẵn dữ liệu giả lập, xem được toàn bộ UI.

---

## Chạy test

```bash
cd src/backend && source .venv/bin/activate
python -m pytest ../../tests/ -q
```

Toàn bộ phải xanh. Nếu có test đỏ ngay sau khi clone, đó là lỗi môi trường — báo cho chúng tôi.

## Nếu vẫn không được

Điền Form 2 phần A với:
- output của `python -m certus doctor`
- nguyên văn thông báo lỗi
- hệ điều hành và phiên bản Python/Node

Đừng mất quá 40 phút. Buổi học có phương án cho người chưa cài được.
