# CERTUS — Trợ lý QA phân tích độ phủ kiểm thử

CERTUS nhận mã nguồn, chạy bộ kiểm, đọc độ phủ và diễn giải bằng hội thoại: phần
nào đã phủ, phần nào còn hở, con số nói lên điều gì (line coverage · mutation
score · grid coverage) và độ tin của chúng.

## Chạy

Backend (FastAPI):

```bash
cd src/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q            # bộ test
uvicorn app.main:app --reload  # API
```

Frontend (React):

```bash
cd src/frontend
npm install
npm run dev
```

Xem `docs/setup.md` để biết chi tiết, và `docs/research-notes/` cho phần lý thuyết
nền (khoảng tin cậy Wilson · grid coverage · chuỗi cổng QA).

## Tài liệu sau buổi học

Buổi workshop chạy trên một bản CERTUS được **cài sẵn lỗ hổng** để tìm. Bản mã
trong repo này là bản **đã vá** — nó khác với bản anh/chị đã dùng trên lớp.

| thư mục | nội dung |
|---|---|
| `patches/` | từng lỗ hổng một, dưới dạng diff — đọc để thấy chính xác đã sửa gì |
| `docs/solutions/` | nguồn sinh ra các diff đó, kèm `DETAILS.md` giải thích từng ca |
| `evidences/`, `reports/` | số liệu nghiệm thu thật: ledger, phân tích, baseline |
| `docs/instructor/live-runbook.md` | kịch bản buổi live, kèm ảnh từng bước |
| `docs/research-notes/` | phần lý thuyết nền (Wilson · grid coverage · chuỗi cổng QA) |

**Lưu ý:** các tệp trong `patches/` neo vào bản **chưa vá**, nên đừng chạy
`git apply` hay `patches/apply-all.sh` trên cây này — nó sẽ báo lỗi vì các sửa
đổi đó *đã nằm sẵn* trong mã. Hãy mở tệp `.patch` ra đọc: nội dung diff tự đủ
nghĩa (dòng `-` là mã có lỗi cũ, dòng `+` là mã đã sửa).
