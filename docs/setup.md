# Cài đặt

Mục tiêu: chạy được CERTUS trên máy bạn trong ~20 phút. Nếu quá 40 phút mà chưa xong, dừng lại và điền lỗi vào Form 2 — chúng tôi sẽ hỗ trợ trước buổi học.

## Yêu cầu

| | Phiên bản | Kiểm tra |
|---|---|---|
| Python | 3.11 trở lên | `python3 --version` |
| Node.js | 18 trở lên | `node --version` |
| Git | bất kỳ | `git --version` |

Không cần Docker. Không cần API key.

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
