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
