# patches/ — lời giải cho các lỗ hổng cài cắm

Mỗi `.patch` là một unified diff **git apply được**, sinh tự động từ SSOT
`docs/solutions/apply_fixes.py` bằng `docs/solutions/emit_patches.py`.
Đừng sửa tay — sửa `apply_fixes.py` rồi chạy lại generator.

Các patch là **tích luỹ theo thứ tự sinh**: nhiều patch cùng một tệp (vd
`analyze.md` mang cả 01 lẫn 07) neo dòng theo trạng thái sau các patch trước.
Vì thế áp TẤT CẢ phải theo đúng thứ tự đó — dùng `apply-all.sh`, đừng
`git apply patches/**/*.patch` (glob sort theo path, sai thứ tự).

```bash
python docs/solutions/emit_patches.py    # sinh lại
bash patches/apply-all.sh                 # áp tất cả (đúng thứ tự tích luỹ)
python docs/solutions/apply_fixes.py      # hoặc áp thẳng từ SSOT (12 bug gốc)
```

Đọc/nghiên cứu một bug: mở tệp `.patch` tương ứng — nội dung diff tự đủ nghĩa.

11 lỗ hổng gốc = golden 12 (khái niệm 01–11; bug 03 gồm 2 nhánh prompt+exec).
Các bản `chat-*` là **surface** trên bề mặt chat mới — cùng khái niệm mẹ,
KHÔNG tính vào mẫu số golden 12.

| lỗ hổng | các bản vá | tệp chạm |
|---|---|---|
| 01-anti-confabulation | `01`, `chat-01`* | src/backend/app/agent/prompts/analyze.md<br>src/backend/app/agent/prompts/chat.md |
| 02-anti-hallucination | `02`, `T-retrieval` | src/backend/app/agent/retrieval.py<br>tests/test_retrieval.py |
| 03-injection | `03a`, `03a-2`, `03b`, `03b-2`, `03a-3`, `T-runner`, `T-project` | src/backend/app/agent/context.py<br>src/backend/app/agent/prompts/system.md<br>src/backend/app/core/exec/runner.py<br>src/backend/app/core/grid/project.py<br>tests/test_project.py<br>tests/test_runner.py |
| 04-coverage-meaning | `04` | src/backend/app/core/grid/rollup.py |
| 05-confidence-interval | `05`, `05-2` | src/backend/app/api/schemas.py<br>src/backend/app/orchestrator/pipeline.py |
| 06-evidence-probe-first | `06`, `06b`, `T-claims`, `chat-06`* | src/backend/app/agent/claims.py<br>src/backend/app/agent/prompts/chat.md<br>tests/test_claims.py |
| 07-deterministic | `07`, `07b`, `chat-07`* | src/backend/app/agent/prompts/analyze.md<br>src/backend/app/agent/prompts/chat.md |
| 08-data-policy | `08`, `08b`, `08c`, `T-redaction` | src/backend/app/policy/redaction.py<br>src/backend/config/data-policy.yaml<br>tests/test_redaction.py |
| 09-authorization | `09` | src/backend/app/auth/scopes.py |
| 10-personalization | `10`, `10b`, `10c`, `10d`, `T-persona` | src/backend/app/agent/persona.py<br>tests/test_persona.py |
| 11-observability | `11`, `11-2`, `11-2b`, `11-3`, `T-tracing` | src/backend/app/observability/logging.py<br>src/backend/app/observability/tracing.py<br>tests/test_tracing.py |

`*` = surface-fix (ngoài golden 12).

## Ghi chú tái hiện (từ audit soi masking 2026-08-06)

- Bug **06** (chỉ tool mới phong OBSERVED) và **07** (tên tool lệch)
  chỉ tái hiện qua flow **analyze** single-shot, KHÔNG qua **chat** —
  không phải bị vá, mà do hai prompt khác nhau cho hai flow khác nhau.
- Bề mặt **chat** tái hiện bug **01** (confabulation) tương đương analyze.
  Các bản `chat-*` ở đây vá cả 01/06/07 cho bề mặt chat.
