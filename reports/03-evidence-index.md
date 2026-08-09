# Chỉ mục bằng chứng

> Sinh tự động bởi `evals/collect.py` lúc 2026-08-06 06:16 UTC.
> Lệnh: `python evals/collect.py`
> **Đừng sửa tay tệp này** — chạy lại script để cập nhật.


Mỗi dòng nối một khẳng định trong `reports/` với tạo tác sinh ra nó.
Không có hash thì *đã chạy và đạt* đọc y hệt *đã viết là đạt*.

| tạo tác | lệnh | exit | sha256 | bytes |
|---|---|---|---|---|
| `pytest-full.txt` | `/home/hieubt15/Documents/ai-product-design-workshop/src/backend/.venv/bin/python -m pytest tests/` | 0 | `818ebf79f42847c4…` | 981 |
| `eval-baseline.txt` | `/home/hieubt15/Documents/ai-product-design-workshop/src/backend/.venv/bin/python evals/run.py --json evidences/eval-baseline.json` | 0 | `84ddb0d40fe3b128…` | 1818 |
| `eval-baseline.json` | `/home/hieubt15/Documents/ai-product-design-workshop/src/backend/.venv/bin/python evals/run.py --json evidences/eval-baseline.json` | 0 | `ca799195a8e2f9d1…` | 4375 |
| `positive-control.txt` | `/home/hieubt15/Documents/ai-product-design-workshop/src/backend/.venv/bin/python evals/run.py --positive-control` | 0 | `e22bce544cb34d55…` | 62 |
| `analyze-shopcart.json` | `/home/hieubt15/Documents/ai-product-design-workshop/src/backend/.venv/bin/python -m certus analyze fixtures/targets/shopcart --json` | 0 | `51041df4a4c10b60…` | 27769 |
| `analyze-ledger.json` | `/home/hieubt15/Documents/ai-product-design-workshop/src/backend/.venv/bin/python -m certus analyze fixtures/targets/ledger --json` | 0 | `13a0be8b2728e571…` | 4745 |
| `analyze-payments.json` | `/home/hieubt15/Documents/ai-product-design-workshop/src/backend/.venv/bin/python -m certus analyze fixtures/targets/payments --json` | 0 | `516fe4b95cb79a50…` | 5175 |
| `ledger.jsonl` | `app.ledger.evidence (append-only)` | 0 | `0a4d5e28eeb5e489…` | 71454 |

Tổng: **8** tạo tác. Bản đầy đủ: `evidences/MANIFEST.json`.
