"""Đọc và sửa cấu hình.

Ai được sửa cái gì ở đây quyết định ai có thể làm cổng ngừng chặn — nên mọi
đường dẫn trong tệp này đều đi qua kiểm quyền, không có ngoại lệ "chỉ đọc thôi
mà".
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends

from app.api.deps import current_principal
from app.auth.scopes import require
from app.contracts.errors import CertusError
from app.settings import settings

router = APIRouter(prefix="/api/config", tags=["config"])

EDITABLE = {"zones.yaml", "grid.yaml", "floor.yaml", "gates.yaml", "data-policy.yaml"}


def _path(name: str) -> Path:
    if name not in EDITABLE:
        raise CertusError(f"{name!r} không nằm trong danh sách tệp cấu hình sửa được")
    return settings.config_dir / name


@router.get("/{name}")
def read_config(name: str, principal=Depends(current_principal)):
    require("config:read")(principal)
    return {"name": name, "content": _path(name).read_text(encoding="utf-8")}


@router.put("/{name}")
def write_config(
    name: str,
    content: str = Body(..., embed=True),
    reason: str = Body(..., embed=True),
    principal=Depends(current_principal),
):
    """Sửa cấu hình. `reason` là bắt buộc.

    Một thay đổi ngưỡng không có lý do đi kèm thì sáu tháng sau không ai dựng
    lại được vì sao nó đổi — và đó là lúc nó bị đổi tiếp.
    """
    require("config:write")(principal)
    if not reason.strip():
        raise CertusError("phải nêu lý do khi đổi cấu hình")

    from app.ledger.evidence import get_ledger

    path = _path(name)
    path.write_text(content, encoding="utf-8")
    get_ledger().append(
        claim_id=f"config:{name}",
        command=f"PUT /api/config/{name}",
        exit_code=0,
        output_sha256="",
        verdict="executed-pass",
        actor=getattr(principal, "sub", None),
    )
    return {"name": name, "written": True, "actor": getattr(principal, "sub", None)}
