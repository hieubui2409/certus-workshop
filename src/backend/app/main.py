"""Ứng dụng FastAPI của CERTUS.

Tệp này chỉ lắp ráp. Mọi quyết định nghiệp vụ nằm ở tầng dưới — nếu một luật
nào đó chỉ tồn tại ở đây thì nó không được test nào bên dưới bảo vệ, và nó sẽ
là thứ đầu tiên trôi đi.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analyze, auth, axes, chat, config, health, ledger, samples, upload
from app.api.schemas import ErrorOut
from app.contracts.errors import CertusError, PermissionDenied
from app.observability import tracing
from app.observability.logging import get_logger, setup_logging
from app.settings import settings

log = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings.ensure_dirs()
    log.info(
        f"CERTUS khởi động · llm_mode={settings.llm_mode} · "
        f"sandbox={settings.sandbox_mode} · model={settings.model}"
    )
    yield


app = FastAPI(
    title="CERTUS",
    description=(
        "Trợ lý QA: đọc mã nguồn, nói cho bạn biết bộ kiểm thử phủ tới đâu, "
        "chỗ nào lỏng, chỗ nào không có cổng chặn nào cả."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Chỉ mở cho frontend dev. Đây là workshop chạy trên máy cá nhân; một `*` ở đây
# sẽ là điều đầu tiên bị chỉ ra, và đúng ra là như vậy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PermissionDenied)
async def _denied(request: Request, exc: PermissionDenied) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content=ErrorOut(
            error="PermissionDenied",
            detail=str(exc),
            trace_id=tracing.current_trace_id(),
            hint="Vai đang dùng không có scope này. Xem config/auth.yaml.",
        ).model_dump(),
    )


@app.exception_handler(CertusError)
async def _certus_error(request: Request, exc: CertusError) -> JSONResponse:
    """Lỗi có cấu trúc ra ngoài nguyên vẹn, kèm trace_id.

    Cố ý KHÔNG gộp thành 500 chung chung: một thông báo "internal server error"
    làm người dùng không phân biệt được "cấu hình thiếu khoá" với "sản phẩm hỏng",
    và họ sẽ thử lại thay vì đi sửa cấu hình.
    """
    return JSONResponse(
        status_code=422,
        content=ErrorOut(
            error=type(exc).__name__,
            detail=str(exc),
            trace_id=tracing.current_trace_id(),
        ).model_dump(),
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(axes.router)
app.include_router(chat.router)
app.include_router(samples.router)
app.include_router(upload.router)
app.include_router(config.router)
app.include_router(ledger.router)
