"""Đọc sổ bằng chứng."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import needs

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


@router.get("")
def tail(limit: int = 100, principal=Depends(needs("gate:read"))):
    from app.ledger.evidence import get_ledger

    records = get_ledger().tail(limit)
    return [r.model_dump(mode="json") for r in records]


@router.get("/verify")
def verify(principal=Depends(needs("gate:read"))):
    """Kiểm tính liền mạch của chuỗi hash.

    Cố ý là một endpoint RIÊNG, không chạy trong `append()`: gọi nó ở đó biến
    mỗi lần ghi thành O(n) và tổng thể thành O(n²) — đã có tiền lệ đo được
    10.000 record mất 36 giây.
    """
    from app.ledger.evidence import get_ledger

    return get_ledger().verify_chain().model_dump(mode="json")
